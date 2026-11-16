import pytest,random
from src.services.grr import grr_analysis,normalize_thresholds,_balanced_anova,_unbalanced_anova
T=normalize_thresholds(None)
META={'standard_count':2,'operators':['O1','O2'],'replicate_count':2}
def readings(cube):
    out=[]
    for (p,o),vals in cube.items():
        for k,v in enumerate(vals,1):
            out.append({'standard_index':1 if p=='P1' else 2,'standard_label':p,'operator':o,'replicate':k,'value':v})
    return out
def test_balanced_closed_form_and_negative_component():
    cube={('P1','O1'):[10,12],('P1','O2'):[14,16],('P2','O1'):[20,22],('P2','O2'):[24,26]}
    r=grr_analysis(META,readings(cube),T)
    assert r['balanced'] and r['n_missing']==0
    ss={x['source']:x['ss'] for x in r['anova']}
    assert abs(ss['标准件（零件间）']-200)<1e-9 and abs(ss['操作员（再现性）']-32)<1e-9
    assert abs(ss['标准件×操作员交互']-0)<1e-9 and abs(ss['重复性（设备内）']-8)<1e-9
    assert abs(ss['合计']-240)<1e-9  # 平衡设计平方和守恒
    vc=r['variance_components']
    assert vc['interaction']==pytest.approx(-1.0)  # 负分量如实保留
    assert vc['grr']==pytest.approx(10.0) and vc['total']==pytest.approx(60.0)  # 汇总在零处截断
    assert any('负方差分量' in x and 'interaction' in x for x in r['handling_notes'])
    assert r['qualified'] is False  # 该玩具数据 GRR 占比/NDC 不达标，负分量本身不判失败
    assert r['anova'][0]['f'] is None  # 交互均方为零，F 记 null 而非 inf
def test_missing_readings_kept_as_null_and_type_iii():
    cube={('P1','O1'):[10,12],('P1','O2'):[14,16],('P2','O1'):[20,22],('P2','O2'):[24,26]}
    data=readings(cube);data[0]['value']=None
    r=grr_analysis(META,data,T)
    assert not r['balanced'] and r['n_missing']==1 and r['missing_ratio']==pytest.approx(1/8)
    assert r['missing_positions']==[{'standard_label':'P1','operator':'O1','replicate':1}]
    assert r['anova'][3]['df']==3  # 缺测后重复性自由度 N-ab = 7-4
    assert 'Type III' in r['method'] and '不插补' in r['method']
def test_empty_cell_is_rejected_not_imputed():
    cube={('P1','O1'):[10,12],('P1','O2'):[14,16],('P2','O1'):[20,22],('P2','O2'):[24,26]}
    data=readings(cube)
    for x in data:
        if x['standard_label']=='P1' and x['operator']=='O1':x['value']=None
    with pytest.raises(ValueError,match='空格'):
        grr_analysis(META,data,T)
def test_interaction_effect_isolated():
    cube={('P1','O1'):[10,10.5],('P1','O2'):[20,20.5],('P2','O1'):[20,20.5],('P2','O2'):[10,10.5]}
    r=grr_analysis(META,readings(cube),T)
    ss={x['source']:x['ss'] for x in r['anova']}
    assert ss['标准件（零件间）']==pytest.approx(0,abs=1e-9)
    assert ss['操作员（再现性）']==pytest.approx(0,abs=1e-9)
    assert ss['标准件×操作员交互']==pytest.approx(200.0)  # 交叉效应被独立分解
def test_threshold_qualification_and_missing_limit():
    # 零件间差异远大于量测噪声 -> 达标（5 标准件跨度 24 N，噪声 0.05 N）
    data=[]
    for i in range(1,6):
        for op in ('O1','O2','O3'):
            for k in range(1,4):
                data.append({'standard_index':i,'standard_label':f'STD-{i}','operator':op,'replicate':k,
                             'value':round(10+6*i+(0.05 if op=='O2' else 0)+0.02*(((i+k)%3)-1),3)})
    r=grr_analysis({'standard_count':5,'operators':['O1','O2','O3'],'replicate_count':3},data,normalize_thresholds(None))
    assert r['qualified'],r['verdict_reasons']
    assert r['metrics']['pct_grr']<10 and r['metrics']['ndc']>=5
    # 自定义阈值：缺测比例超阈即不达标
    data[0]['value']=None
    strict=normalize_thresholds({'max_missing_ratio':0.005})
    r2=grr_analysis({'standard_count':5,'operators':['O1','O2','O3'],'replicate_count':3},data,strict)
    assert not r2['qualified'] and any('缺测比例' in x for x in r2['verdict_reasons'])
def test_threshold_validation():
    with pytest.raises(ValueError):normalize_thresholds({'grr_percent_max':0})
    with pytest.raises(ValueError):normalize_thresholds({'ndc_min':0})
    with pytest.raises(ValueError):normalize_thresholds({'max_missing_ratio':1})
def test_balanced_and_type_iii_engines_agree_on_complete_design():
    # effects 编码下效应空间正交：完整设计的 OLS Type III 必须与闭式解逐项一致
    rng=random.Random(9);a,b,r=3,2,3
    cube=[[[round(20+4*i+rng.gauss(0,1),3) for _ in range(r)] for j in range(b)] for i in range(a)]
    obs=[(i,j,k,cube[i][j][k]) for i in range(a) for j in range(b) for k in range(r)]
    closed=_balanced_anova(cube,a,b,r);ols=_unbalanced_anova(obs,a,b)
    for x,y in zip(closed,ols):assert x==pytest.approx(y,abs=1e-9)
def test_repeatability_zero_variance_fails():
    data=[]
    for i in (1,2):
        for op in ('O1','O2'):
            for k in (1,2):
                data.append({'standard_index':i,'standard_label':f'P{i}','operator':op,'replicate':k,
                             'value':float(10*i+(2 if op=='O2' else 0))})  # 重复读数完全相同
    with pytest.raises(ValueError,match='重复性均方为零'):
        grr_analysis(META,data,T)
