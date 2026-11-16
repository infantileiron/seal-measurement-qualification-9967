import{request,post}from'./client.js';
export const list=()=>request('/gauge-studies');
export const detail=id=>request('/gauge-studies/'+id);
export const create=data=>post('/gauge-studies',data);
export const saveReadings=(id,readings)=>request('/gauge-studies/'+id+'/readings',{method:'PUT',body:JSON.stringify({readings})});
export const publish=id=>post('/gauge-studies/'+id+'/publish',{});
export const isolation=()=>request('/isolation');
