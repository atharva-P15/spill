import {useEffect,useRef} from 'react';
import * as monaco from 'monaco-editor';
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker';
self.MonacoEnvironment={getWorker:()=>new EditorWorker()};

export default function Code({original,value,onChange,diff=false}){
 const container=useRef(null),models=useRef(null),callback=useRef(onChange);
 callback.current=onChange;
 useEffect(()=>{
  monaco.editor.setTheme('vs-dark');
  const options={minimap:{enabled:false},occurrencesHighlight:'off',selectionHighlight:false,fontSize:13,fontFamily:'Consolas, monospace',padding:{top:18},scrollBeyondLastLine:false,automaticLayout:true,wordWrap:'on'};
  const modified=monaco.editor.createModel(value,'python');
  const before=diff?monaco.editor.createModel(original,'python'):null;
  const editor=diff?monaco.editor.createDiffEditor(container.current,{...options,readOnly:true,renderSideBySide:true}):monaco.editor.create(container.current,{...options,model:modified});
  if(diff)editor.setModel({original:before,modified});
  const subscription=modified.onDidChangeContent(()=>callback.current?.(modified.getValue()));
  models.current={modified,before};
  return ()=>{
   subscription.dispose();
   // Detach before disposing: diff workers must release their references first.
   editor.setModel(null);editor.dispose();modified.dispose();before?.dispose();
   models.current=null;
  };
 },[diff]);
 useEffect(()=>{const m=models.current?.modified;if(m&&m.getValue()!==value)m.setValue(value);},[value]);
 useEffect(()=>{const m=models.current?.before;if(m&&m.getValue()!==original)m.setValue(original);},[original]);
 return <div ref={container} style={{height:470,width:'100%'}} aria-label={diff?'Code difference preview':'Python code editor'}/>;
}
