/** @typedef {{id:number,code:string,name:string,process_id:number,lot:string,force:number,flagged:boolean,note:string,device_id:number|null,disposition:'normal'|'quarantined'|'released',hold_reason:string}} Sample */
/** @typedef {{id:number,code:string,name:string,status:'unqualified'|'qualified'|'requalifying',note:string}} Device */
/** @typedef {{id:number,code:string,device_id:number,title:string,standard_count:number,operators:string[],replicate_count:number,thresholds:object,status:string,result:object|null,published:boolean}} GaugeStudy */
export const contractsVersion='seal-variance-2';
