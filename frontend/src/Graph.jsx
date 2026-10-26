import {useMemo,useState} from 'react';
import {ReactFlow,Background,Controls,MiniMap,MarkerType} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
export default function Graph({data,report,onSelect}){
 const [filter,setFilter]=useState(''),[historical,setHistorical]=useState(true),[selected,setSelected]=useState(null);
 const derived=useMemo(()=>{
  if(!data)return {nodes:[],edges:[],total:0};
  const impacts=new Map((report?.impacted_files||[]).map(r=>[r.file,r]));
  const ordered=[...data.nodes].sort((a,b)=>(a.id===report?.changed_file?-1:b.id===report?.changed_file?1:0)||((impacts.has(b.id)?1:0)-(impacts.has(a.id)?1:0))||a.id.localeCompare(b.id));
  const visible=ordered.filter(n=>n.id.toLowerCase().includes(filter.toLowerCase())).slice(0,100);
  const ids=new Set(visible.map(n=>n.id));
  const nodes=visible.map((n,i)=>{const row=impacts.get(n.id),changed=n.id===report?.changed_file;
   return {id:n.id,position:{x:(i%4)*260,y:Math.floor(i/4)*110},data:{label:n.id},style:{background:changed?'#244c40':'#1a2422',color:changed?'#b9f8ce':'#d8e5df',border:'1px solid '+(changed?'#a4efbf':row?.risk==='HIGH'?'#f48787':row?.distance===1?'#c8a867':'#3b5049'),borderRadius:10,width:220,fontSize:11,padding:14}};
  });
  const edges=[...data.edges,...(historical?data.historical.map(e=>({...e,kind:'history'})):[])].filter(e=>ids.has(e.source)&&ids.has(e.target)).map((e,i)=>({id:'e'+i,source:e.source,target:e.target,animated:!!report&&impacts.has(e.source),style:{stroke:e.kind==='history'?'#8279ba':'#557668',strokeDasharray:e.kind==='history'?'5 5':undefined},markerEnd:e.kind==='history'?undefined:{type:MarkerType.ArrowClosed},label:e.kind==='history'?'co-change':undefined}));
  return {nodes,edges,total:data.nodes.length};
 },[data,filter,historical,report]);
 return <section className="graph-panel"><div className="graph-tools"><input aria-label="Filter graph" placeholder="Filter files…" value={filter} onChange={e=>setFilter(e.target.value)}/><label><input type="checkbox" checked={historical} onChange={e=>setHistorical(e.target.checked)}/> Historical links</label><span>{derived.nodes.length} / {derived.total} files</span></div><div style={{height:420}}><ReactFlow nodes={derived.nodes} edges={derived.edges} fitView onNodeClick={(_,n)=>{setSelected(n.id);onSelect?.(n.id);}} colorMode="dark"><Background color="#34453f" gap={22}/><Controls/><MiniMap pannable zoomable nodeColor="#639b7d"/></ReactFlow></div><div className="graph-caption">{selected?<span>Selected: <b>{selected}</b></span>:<span>Select a node to inspect its file.</span>}<span>Arrow: importer → dependency · Dashed: historical co-change</span></div></section>;
}
