import { useEffect, useState } from "react";
import { Action, ActionPanel, Form, List, showToast, Toast, closeMainWindow } from "@vicinae/api";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
const exec = promisify(execFile);
type State = {iosAlbumArt:boolean;layout:string;layouts:{id:string;title:string}[];theme:string;themeAvailable:boolean;styleTui:boolean;styleBackground:boolean;monitor:string;monitors:string[];player:string;players:string[];widgets:{id:string;title:string;visible:boolean}[]};
async function control(request:object):Promise<State> {
  await exec("systemctl",["--user","start","glass-dashboard.service"],{timeout:10000});
  const result=await exec(`${homedir()}/.local/bin/glass-dashboard`,["--control",JSON.stringify(request)],{timeout:15000});
  return JSON.parse(result.stdout);
}
function MusicAppearance({initial,onUpdate}:{initial:State;onUpdate:(state:State)=>void}) {
  const [enabled,setEnabled]=useState(initial.iosAlbumArt);
  const [busy,setBusy]=useState(false);
  async function change(value:boolean) {
    if(busy)return;
    setBusy(true);
    try {const next=await control({action:"iosAlbumArt",value});setEnabled(next.iosAlbumArt);onUpdate(next);}
    catch(e){await showToast({style:Toast.Style.Failure,title:"Music appearance update failed",message:String(e)});}
    finally{setBusy(false);}
  }
  return <Form navigationTitle="Music appearance" isLoading={busy}>
    <Form.Checkbox id="iosAlbumArt" label="iOS album art colors" value={enabled} onChange={change} />
    <Form.Description text="Use softly blurred artwork colors for the player. Colors remain while paused; missing artwork uses the dashboard theme. Changes save immediately." />
  </Form>;
}
export default function DashboardControls(){
  const [state,setState]=useState<State>(); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function act(request:object,close=false){
    setBusy(true);
    try {setState(await control(request));setError("");if(close)await closeMainWindow();}
    catch(e){const message=String(e);setError(message);await showToast({style:Toast.Style.Failure,title:"Dashboard action failed",message});}
    finally{setBusy(false);}
  }
  useEffect(()=>{void act({action:"status"});},[]);
  const row=(id:string,title:string,value:string,request:object,close=false)=><List.Item key={id} id={id} title={title} accessories={[{text:value}]} actions={<ActionPanel><Action title={title} onAction={()=>act(request,close)}/><Action title="Refresh Controls" onAction={()=>act({action:"status"})}/></ActionPanel>}/>;
  return <List isLoading={busy} navigationTitle="Dashboard Controls" searchBarPlaceholder="Search settings, widgets, displays…">
    {!state&&<List.EmptyView title={error?"Dashboard unavailable":"Loading dashboard…"} description={error} actions={<ActionPanel><Action title="Retry" onAction={()=>act({action:"status"})}/></ActionPanel>}/>}
    {state&&<>
      <List.Section title="Layout">
        {state.layouts.map(layout=>row(`layout-${layout.id}`,layout.title,state.layout===layout.id?"✓ Selected":"",{action:"layout",value:layout.id}))}
      </List.Section>
      <List.Section title="Btop" subtitle={state.theme!=="full"?"Select Full Theme in Theme Settings to change styling":""}>
        {state.theme==="full" ? <>
          {row("tui","Style TUI",state.styleTui?"On":"Off",{action:"styleTui",value:!state.styleTui})}
          {row("background","Style Background",state.styleBackground?"On":"Off",{action:"styleBackground",value:!state.styleBackground})}
        </> : <List.Item title="Btop styling requires Full Theme"/>}
        {row("terminal","Restart Btop","",{action:"restartTerminal"})}
      </List.Section>
      <List.Section title="Widgets">{state.widgets.map(w=>row(w.id,w.title,w.visible?"Visible":"Hidden",{action:"visibility",widget:w.id,value:!w.visible}))}</List.Section>
      <List.Section title="Display">{state.monitors.map(m=>row(`display-${m}`,m,state.monitor===m?"✓ Selected":"",{action:"monitor",value:m}))}</List.Section>
      <List.Section title="Music Player"><List.Item title="Music appearance" accessories={[{text:state.iosAlbumArt?"iOS colors on":"iOS colors off"}]} actions={<ActionPanel><Action.Push title="Configure Music Appearance" target={<MusicAppearance initial={state} onUpdate={setState}/>} /></ActionPanel>} />{["",...state.players].map(p=>row(`player-${p}`,p.replace("org.mpris.MediaPlayer2.","")||"Automatic",state.player===p?"✓ Selected":"",{action:"player",value:p}))}</List.Section>
      <List.Section title="Recovery"><List.Item title="Restart Dashboard" actions={<ActionPanel><Action title="Restart Dashboard" onAction={async()=>{setBusy(true);try{await exec("systemctl",["--user","restart","glass-dashboard.service"],{timeout:10000});await act({action:"status"});}catch(e){setBusy(false);await showToast({style:Toast.Style.Failure,title:"Restart failed",message:String(e)});}}}/></ActionPanel>}/></List.Section>
    </>}
  </List>;
}
