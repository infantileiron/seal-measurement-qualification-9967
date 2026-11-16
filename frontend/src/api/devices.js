import{request,post}from'./client.js';export const list=()=>request('/devices');export const save=(data,id)=>id?request('/devices/'+id,{method:'PUT',body:JSON.stringify(data)}):post('/devices',data);
