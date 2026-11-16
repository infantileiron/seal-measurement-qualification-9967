import json,hashlib,math
from scipy.stats import f
from src.constants.enums import DEFAULT_GRR_PERCENT_MAX,DEFAULT_NDC_MIN,DEFAULT_MAX_MISSING_RATIO

# 交叉型量测系统分析（标准件 × 操作员 × 重复次数），AIAG MSA 双因素有重复 ANOVA 口径。
# 缺测不插补、不剔除整行：完整平衡走教科书闭式解；存在缺测走 OLS Type III 偏平方和，
# 方差分量除数改用单元格调和均值（Searle 不平衡设计口径），两类口径在平衡时完全一致。

def _solve_normal(xtx,xty):
    # 高斯消元（列主元）解正规方程；返回系数与秩，秩不足即设计矩阵缺格不可估
    n=len(xtx);a=[row[:]+[xty[i]] for i,row in enumerate(xtx)];rank=0
    scale=max(1e-12,max(abs(a[i][j]) for i in range(n) for j in range(n)))
    pivots=[];col=0
    for row in range(n):
        while col<n:
            pivot=max(range(row,n),key=lambda r:abs(a[r][col]))
            if abs(a[pivot][col])<=1e-10*scale:col+=1;continue
            break
        if col==n:break
        a[row],a[pivot]=a[pivot],a[row]
        div=a[row][col]
        for j in range(col,n+1):a[row][j]/=div
        for r in range(n):
            if r==row:continue
            factor=a[r][col]
            if abs(factor)>1e-14:
                for j in range(col,n+1):a[r][j]-=factor*a[row][j]
        pivots.append(col);rank+=1;col+=1
    if rank<n:raise ValueError('设计矩阵秩不足：存在标准件×操作员空格或有效读数过少，无法估计交互与重复变异')
    beta=[0.0]*n
    for i,c in enumerate(pivots):beta[c]=a[i][n]
    return beta

def _effects_code(level,n):
    # 总和为零（sum-to-zero / effects）编码：末水平为各列 -1，其余为指示变量。
    # 平衡设计下各效应列空间彼此正交，删列偏平方和即经典 ANOVA SS；
    # 不平衡时仍给出 Type III 可估计函数（参考组 0/1 哑变量编码与交互列非正交，不能用于此假设）。
    return [1.0 if t==level else (-1.0 if level==n-1 else 0.0) for t in range(n-1)]

def _design_matrix(obs,a,b,drop_part=False,drop_operator=False,drop_interaction=False):
    # 全模型列：截距 1 + 标准件(a-1) + 操作员(b-1) + 交互((a-1)(b-1))
    rows=[];yv=[]
    for i,j,k,y in obs:
        row=[1.0]
        part=_effects_code(i,a) if not drop_part else []
        oper=_effects_code(j,b) if not drop_operator else []
        inter=[]
        if not drop_interaction:
            pc=_effects_code(i,a);oc=_effects_code(j,b)
            inter=[x*z for x in pc for z in oc]
        rows.append(row+part+oper+inter);yv.append(y)
    p=len(rows[0])
    xtx=[[0.0]*p for _ in range(p)];xty=[0.0]*p
    for row,y in zip(rows,yv):
        for u in range(p):
            xty[u]+=row[u]*y
            for v in range(p):xtx[u][v]+=row[u]*row[v]
    beta=_solve_normal(xtx,xty)
    sse=sum((y-sum(row[t]*beta[t] for t in range(p)))**2 for row,y in zip(rows,yv))
    return sse

def _balanced_anova(cube,a,b,r):
    grand=sum(v for layer in cube for row in layer for v in row)/(a*b*r)
    part_means=[sum(cube[i][j][k] for j in range(b) for k in range(r))/(b*r) for i in range(a)]
    oper_means=[sum(cube[i][j][k] for i in range(a) for k in range(r))/(a*r) for j in range(b)]
    cell_means=[[sum(cube[i][j])/r for j in range(b)] for i in range(a)]
    ss_part=b*r*sum((m-grand)**2 for m in part_means)
    ss_operator=a*r*sum((m-grand)**2 for m in oper_means)
    ss_interaction=r*sum((cell_means[i][j]-part_means[i]-oper_means[j]+grand)**2 for i in range(a) for j in range(b))
    ss_repeat=sum((cube[i][j][k]-cell_means[i][j])**2 for i in range(a) for j in range(b) for k in range(r))
    ss_total=sum((cube[i][j][k]-grand)**2 for i in range(a) for j in range(b) for k in range(r))
    return grand,ss_part,ss_operator,ss_interaction,ss_repeat,ss_total

def _unbalanced_anova(obs,a,b):
    n=len(obs);grand=sum(y for *_,y in obs)/n
    sst=sum((y-grand)**2 for *_,y in obs)
    sse_full=_design_matrix(obs,a,b)
    sse_no_part=_design_matrix(obs,a,b,drop_part=True)
    sse_no_operator=_design_matrix(obs,a,b,drop_operator=True)
    sse_no_interaction=_design_matrix(obs,a,b,drop_interaction=True)
    ss_part=sse_no_part-sse_full
    ss_operator=sse_no_operator-sse_full
    ss_interaction=sse_no_interaction-sse_full
    return grand,ss_part,ss_operator,ss_interaction,sse_full,sst

def grr_analysis(meta,readings,thresholds):
    a=meta['standard_count'];operators=meta['operators'];b=len(operators);r=meta['replicate_count']
    if a<2 or b<2 or r<2:raise ValueError('标准件数、操作员数与重复次数均至少为 2，才能分解交互与重复变异')
    cube=[[[None]*r for _ in range(b)] for _ in range(a)]
    labels={};missing=[]
    op_index={name:j for j,name in enumerate(operators)}
    for rd in readings:
        i=rd['standard_index']-1;j=op_index[rd['operator']];k=rd['replicate']-1
        if not (0<=i<a and 0<=j<b and 0<=k<r):raise ValueError('读数坐标超出试验设计范围')
        cube[i][j][k]=rd['value'];labels[i]=rd['standard_label']
        if rd['value'] is None:
            missing.append({'standard_label':rd['standard_label'],'operator':rd['operator'],'replicate':rd['replicate']})
    cell_sizes=[[sum(1 for v in cube[i][j] if v is not None) for j in range(b)] for i in range(a)]
    empty=[f"{labels[i]} × {operators[j]}" for i in range(a) for j in range(b) if cell_sizes[i][j]==0]
    if empty:raise ValueError('标准件×操作员存在空格（'+'、'.join(empty)+'），交互项不可估；补齐至少一次读数后重测，不做插补')
    total_cells=a*b*r;n_observed=total_cells-len(missing);missing_ratio=len(missing)/total_cells
    balanced=not missing
    df_part=a-1;df_operator=b-1;df_interaction=(a-1)*(b-1);df_repeat=a*b*(r-1)
    if balanced:
        grand,ss_part,ss_operator,ss_interaction,ss_repeat,ss_total=_balanced_anova(cube,a,b,r)
        divisor_part=b*r;divisor_operator=a*r;divisor_interaction=r
        ss_conservation=abs(ss_total-(ss_part+ss_operator+ss_interaction+ss_repeat))
        if ss_conservation>1e-8*max(1.0,ss_total):raise ValueError('平方和守恒校验失败，读数矩阵与设计不一致')
    else:
        obs=[(i,j,k,cube[i][j][k]) for i in range(a) for j in range(b) for k in range(r) if cube[i][j][k] is not None]
        grand,ss_part,ss_operator,ss_interaction,ss_repeat,ss_total=_unbalanced_anova(obs,a,b)
        df_repeat=n_observed-a*b  # 每单元格截距占一个自由度
        # 不平衡除数（Searle）：单元格调和均值及操作员/标准件边际调和均值，平衡时退化为 r、ar、br
        n_harmonic=a*b/sum(1.0/cell_sizes[i][j] for i in range(a) for j in range(b))
        oper_totals=[sum(cell_sizes[i][j] for i in range(a)) for j in range(b)]
        part_totals=[sum(cell_sizes[i]) for i in range(a)]
        divisor_interaction=n_harmonic
        divisor_operator=b/sum(1.0/oper_totals[j] for j in range(b))
        divisor_part=a/sum(1.0/part_totals[i] for i in range(a))
    df_repeat=max(df_repeat,0)
    if df_repeat<1:raise ValueError('有效读数不足，重复性自由度为 0；请补齐缺测后重测')
    ms_part=ss_part/df_part;ms_operator=ss_operator/df_operator
    ms_interaction=ss_interaction/df_interaction;ms_repeat=ss_repeat/df_repeat
    if ms_repeat<=1e-12:raise ValueError('重复性均方为零，F 检验与方差分量不成立；需补充有实际测量差异的读数')
    def _ratio(num,den,dfn,dfd):
        # 分母均方为零时 F 不成立（如交互恰好无变异）：如实记 null，不用无穷值污染导出 JSON
        if den<=1e-12:return None,None
        stat=num/den
        return stat,float(f.sf(stat,dfn,dfd))
    f_part,p_part=_ratio(ms_part,ms_interaction,df_part,df_interaction)
    f_operator,p_operator=_ratio(ms_operator,ms_interaction,df_operator,df_interaction)
    f_interaction,p_interaction=_ratio(ms_interaction,ms_repeat,df_interaction,df_repeat)
    # 方差分量：负值如实保留并在结论中说明；汇总口径按 AIAG 在零处截断，避免负总方差
    vc_repeat=ms_repeat
    vc_interaction=(ms_interaction-ms_repeat)/divisor_interaction
    vc_operator=(ms_operator-ms_interaction)/divisor_operator
    vc_part=(ms_part-ms_interaction)/divisor_part
    raw={'part':vc_part,'operator':vc_operator,'interaction':vc_interaction,'repeatability':vc_repeat}
    negative=[key for key,v in raw.items() if v<0]
    floor={k:max(0.0,v) for k,v in raw.items()}
    vc_grr=floor['repeatability']+floor['operator']+floor['interaction']
    vc_total=vc_grr+floor['part']
    sd=lambda v:math.sqrt(max(0.0,v))
    grr_sd=sd(vc_grr);total_sd=sd(vc_total);part_sd=sd(floor['part'])
    ev_sd=sd(floor['repeatability']);av_sd=sd(floor['operator']+floor['interaction'])
    pct_grr=(grr_sd/total_sd*100) if total_sd>1e-12 else 0.0
    ndc=(1.41*part_sd/grr_sd) if grr_sd>1e-12 else 0.0
    contributions={k:(floor[k]/vc_total*100 if vc_total>1e-12 else 0.0) for k in floor}
    checks={
        'missing_ratio':{'value':missing_ratio,'limit':thresholds['max_missing_ratio'],'pass':missing_ratio<=thresholds['max_missing_ratio']},
        'grr_percent':{'value':pct_grr,'limit':thresholds['grr_percent_max'],'pass':pct_grr<=thresholds['grr_percent_max']},
        'ndc':{'value':ndc,'limit':thresholds['ndc_min'],'pass':ndc>=thresholds['ndc_min']},
    }
    reasons=[];notes=[]
    if not checks['missing_ratio']['pass']:reasons.append(f"缺测比例 {missing_ratio:.1%} 超过阈值 {thresholds['max_missing_ratio']:.1%}")
    if not checks['grr_percent']['pass']:reasons.append(f"GR&R 研究变异占比 {pct_grr:.2f}% 超过阈值 {thresholds['grr_percent_max']:.2f}%")
    if not checks['ndc']['pass']:reasons.append(f"可区分类别数 NDC={ndc:.2f} 低于阈值 {thresholds['ndc_min']}")
    # 负方差分量是 ANOVA 法常见估计现象：按 AIAG 截断为零参与汇总，属处理说明而非不合格项
    if negative:notes.append('负方差分量（'+'、'.join(negative)+'）为 ANOVA 估计噪声所致，按 AIAG 在零处截断参与汇总；原始负值保留在 variance_components 中')
    anova_rows=[
        {'source':'标准件（零件间）','ss':ss_part,'df':df_part,'ms':ms_part,'f':f_part,'p':p_part},
        {'source':'操作员（再现性）','ss':ss_operator,'df':df_operator,'ms':ms_operator,'f':f_operator,'p':p_operator},
        {'source':'标准件×操作员交互','ss':ss_interaction,'df':df_interaction,'ms':ms_interaction,'f':f_interaction,'p':p_interaction},
        {'source':'重复性（设备内）','ss':ss_repeat,'df':df_repeat,'ms':ms_repeat,'f':None,'p':None},
        {'source':'合计','ss':ss_total,'df':n_observed-1,'ms':None,'f':None,'p':None},
    ]
    canonical=json.dumps({'meta':meta,'readings':sorted(readings,key=lambda x:(x['standard_index'],x['operator'],x['replicate']))},sort_keys=True,ensure_ascii=False,default=str)
    method=('交叉型 Gauge R&R 双因素有重复 ANOVA；F 检验以交互均方为标准件/操作员分母、重复均方为交互分母。'
            +('平衡设计，平方和可加且守恒。' if balanced else '存在缺测，采用总和为零（effects）编码的 OLS Type III 偏平方和与调和均值除数，效应空间在平衡时正交、缺测时仍给出 Type III 可估计函数；偏平方和不要求可加；缺测保留 null 不插补。')
            +'负方差分量如实列示、汇总时在零处截断（AIAG MSA）。%GRR 与 NDC 按 6σ 研究变异口径；<10% 合格、10–30% 视场景接受、>30% 不合格。')
    return {'balanced':balanced,'n_observed':n_observed,'n_cells':total_cells,'n_missing':len(missing),
            'missing_ratio':missing_ratio,'missing_positions':missing,'grand_mean':grand,
            'anova':anova_rows,'variance_components':{**raw,'grr':vc_grr,'total':vc_total},
            'metrics':{'ev_sd':ev_sd,'av_sd':av_sd,'grr_sd':grr_sd,'part_sd':part_sd,'total_sd':total_sd,
                       'pct_grr':pct_grr,'ndc':ndc,'contributions':contributions},
            'thresholds':thresholds,'checks':checks,'qualified':not reasons,
            'verdict_reasons':reasons,'handling_notes':notes,
            'checksum':hashlib.sha256(canonical.encode()).hexdigest(),'method':method}

def normalize_thresholds(raw):
    t={'grr_percent_max':DEFAULT_GRR_PERCENT_MAX,'ndc_min':DEFAULT_NDC_MIN,'max_missing_ratio':DEFAULT_MAX_MISSING_RATIO}
    if raw is not None:
        raw=raw.model_dump() if hasattr(raw,'model_dump') else raw
        for k in t:
            if k in raw and raw[k] is not None:t[k]=raw[k]
    if not (0<t['grr_percent_max']<=100):raise ValueError('GR&R 百分比阈值需在 (0,100] 内')
    if not (1<=t['ndc_min']<=50):raise ValueError('NDC 阈值需在 1–50 之间')
    if not (0<=t['max_missing_ratio']<1):raise ValueError('缺测比例阈值需在 [0,1) 内')
    t['ndc_min']=int(t['ndc_min'])
    return t
