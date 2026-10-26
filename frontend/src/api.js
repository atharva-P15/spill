import axios from 'axios';
export const api=axios.create({baseURL:import.meta.env.VITE_API_URL||'/api',timeout:180000});
api.interceptors.request.use(config=>{const token=sessionStorage.getItem('spill-token');if(token)config.headers.Authorization='Bearer '+token;return config;});
export function errorMessage(error){const d=error.response?.data?.detail;return typeof d==='string'?d:Array.isArray(d)?d.map(e=>e.msg).join('; '):error.message||'The request failed.';}
export function summarize(repos,analyses){return {repositories:repos.length,analyses:analyses.length,high:analyses.filter(a=>a.risk==='HIGH').length,low:analyses.filter(a=>a.risk==='LOW').length};}

