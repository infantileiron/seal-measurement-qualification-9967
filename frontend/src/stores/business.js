import{list as processes}from'../api/processes.js';import{list as samples}from'../api/samples.js';import{list as assessments}from'../api/assessments.js';import{list as devices}from'../api/devices.js';import{list as studies,isolation}from'../api/gauge.js';
export const store={user:null,processes:[],samples:[],assessments:[],devices:[],studies:[],held:[],active:null,review:null,study:null};
export async function refresh(){
  [store.processes,store.samples,store.assessments,store.devices,store.studies,store.held]=
    await Promise.all([processes(),samples(),assessments(),devices(),studies(),isolation()]);
}
export function active(){return store.assessments.find(a=>a.id===store.active)||store.assessments[0];}
