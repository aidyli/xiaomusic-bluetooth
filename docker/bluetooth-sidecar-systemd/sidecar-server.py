#!/usr/bin/env python3
import json, os, subprocess, time, urllib.parse, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ADDR=os.environ.get('BT_TARGET_MAC','44:F7:70:81:9C:C4')
PORT=int(os.environ.get('BT_BRIDGE_PORT','58091'))
SINK=os.environ.get('BT_SINK','')
MPV_PROC=None
STATE={'scan': {'running': False, 'last': None}, 'connect': {'running': False, 'last': None}}
LOCK=threading.Lock()

def run(cmd, timeout=20):
    try:
        p=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {'returncode':p.returncode,'stdout':p.stdout[-6000:],'stderr':p.stderr[-6000:]}
    except subprocess.TimeoutExpired as e:
        return {'returncode':124,'stdout':(e.stdout or '')[-6000:] if isinstance(e.stdout,str) else '', 'stderr':((e.stderr or '')[-6000:] if isinstance(e.stderr,str) else '') + ' TIMEOUT'}
    except Exception as e:
        return {'returncode':255,'stdout':'','stderr':f'{type(e).__name__}: {e}'}

def get_sink():
    global SINK
    if SINK:
        return SINK
    p=run(['pactl','list','short','sinks'], timeout=5)
    for line in p.get('stdout','').splitlines():
        parts=line.split('\t')
        if len(parts)>1 and ('bluez' in parts[1] or ADDR.replace(':','_') in parts[1]):
            SINK=parts[1]
            return SINK
    return ''

def scan_blocking(seconds=20):
    steps=[]
    # reset / enable controller and force classic BR/EDR discovery as many A2DP speakers do not behave like BLE devices
    for cmd, tout in [
        (['rfkill','unblock','bluetooth'],5),
        (['btmgmt','power','off'],8),
        (['btmgmt','power','on'],8),
        (['btmgmt','bredr','on'],8),
        (['btmgmt','le','on'],8),
        (['bluetoothctl','power','on'],5),
        (['bluetoothctl','pairable','on'],5),
    ]:
        steps.append({'cmd':cmd, **run(cmd,tout)})
    # btmgmt find tends to expose lower-level discovery issues better than bluetoothctl
    steps.append({'cmd':['timeout',str(seconds),'btmgmt','find'], **run(['timeout',str(seconds),'btmgmt','find'],seconds+5)})
    # bluetoothctl supports menu scan/transport bredr interactively; feed commands over stdin
    bredr_cmd='printf "menu scan\ntransport bredr\nback\nscan on\n" | timeout '+str(seconds)+' bluetoothctl'
    steps.append({'cmd':['bash','-lc',bredr_cmd], **run(['bash','-lc',bredr_cmd],seconds+5)})
    steps.append({'cmd':['timeout',str(seconds),'bluetoothctl','scan','on'], **run(['timeout',str(seconds),'bluetoothctl','scan','on'],seconds+5)})
    steps.append({'cmd':['timeout',str(max(8, seconds//2)),'hcitool','scan'], **run(['timeout',str(max(8, seconds//2)),'hcitool','scan'],max(12,seconds//2+5))})
    devices=run(['bluetoothctl','devices'],5)
    info=run(['bluetoothctl','info',ADDR],5)
    return {'steps':steps,'devices':devices,'target_info':info,'found': info.get('returncode')==0 or ADDR in devices.get('stdout','') or any(ADDR in str(x) for x in steps)}

def connect_blocking(scan_if_missing=True):
    out=[]
    info0=run(['bluetoothctl','info',ADDR], timeout=5)
    out.append({'cmd':['bluetoothctl','info',ADDR], **info0})
    if scan_if_missing and info0.get('returncode') != 0:
        out.append({'phase':'scan', **scan_blocking(25)})
    for cmd in ([['bluetoothctl','power','on'], ['bluetoothctl','pairable','on'], ['bluetoothctl','agent','NoInputNoOutput'], ['bluetoothctl','default-agent'], ['bluetoothctl','pair',ADDR], ['bluetoothctl','trust',ADDR], ['bluetoothctl','connect',ADDR]]):
        out.append({'cmd':cmd, **run(cmd, timeout=30)})
    time.sleep(3)
    info=run(['bluetoothctl','info',ADDR],5)
    sinks=run(['pactl','list','short','sinks'],5)
    return {'steps':out,'device':info,'sink':get_sink(), 'sinks': sinks, 'connected':'Connected: yes' in info.get('stdout','')}

def start_job(kind, fn):
    with LOCK:
        if STATE[kind]['running']:
            return {'started':False,'running':True,'last':STATE[kind]['last']}
        STATE[kind]['running']=True
    def worker():
        res=fn()
        with LOCK:
            STATE[kind]['last']=res
            STATE[kind]['running']=False
    threading.Thread(target=worker, daemon=True).start()
    return {'started':True,'running':True}

def stop():
    global MPV_PROC
    rc=None
    if MPV_PROC and MPV_PROC.poll() is None:
        MPV_PROC.terminate()
        try: MPV_PROC.wait(timeout=4)
        except subprocess.TimeoutExpired:
            MPV_PROC.kill(); MPV_PROC.wait(timeout=4)
        rc=MPV_PROC.returncode
    MPV_PROC=None
    subprocess.run(['pkill','-f','mpv.*bluez'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'stopped':True,'returncode':rc}

def play(url):
    global MPV_PROC
    stop()
    c=connect_blocking(scan_if_missing=False)
    sink=get_sink()
    if not sink:
        return {'ok':False,'error':'no_bluez_sink','connect':c}, 500
    cmd=['mpv','--no-video','--ao=pulse',f'--audio-device=pulse/{sink}',url]
    MPV_PROC=subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'ok':True,'action':'play','pid':MPV_PROC.pid,'sink':sink}, 200

def status_obj():
    return {'ok':True,'sink':get_sink(),'jobs':STATE,'sinks':run(['pactl','list','short','sinks'],5),'controller':run(['bluetoothctl','show'],5),'device':run(['bluetoothctl','info',ADDR],5),'processes':run(['bash','-lc','pgrep -af "mpv|bluetoothd|pulseaudio" || true'],5)}

class H(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        data=json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('content-type','application/json; charset=utf-8'); self.send_header('content-length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); qs=urllib.parse.parse_qs(u.query)
        try:
            if u.path=='/health': self._send({'ok':True,'sink':get_sink(),'scan_running':STATE['scan']['running'],'connect_running':STATE['connect']['running']})
            elif u.path=='/status' or u.path=='/debug': self._send(status_obj())
            elif u.path=='/scan':
                async_mode=qs.get('async',['1'])[0] != '0'
                if async_mode: self._send({'ok':True,'action':'scan',**start_job('scan', lambda: scan_blocking(int(qs.get('seconds',['25'])[0])) )})
                else: self._send({'ok':True,'action':'scan', **scan_blocking(int(qs.get('seconds',['25'])[0]))})
            elif u.path=='/connect':
                async_mode=qs.get('async',['1'])[0] != '0'
                if async_mode: self._send({'ok':True,'action':'connect',**start_job('connect', lambda: connect_blocking(True))})
                else: self._send({'ok':True,'action':'connect',**connect_blocking(True)})
            elif u.path=='/stop': self._send({'ok':True,'action':'stop',**stop()})
            elif u.path=='/disconnect':
                s=stop(); d=run(['bluetoothctl','disconnect',ADDR],15); self._send({'ok':d['returncode']==0,'action':'disconnect','stop':s,'disconnect':d})
            elif u.path=='/play':
                url=qs.get('url',[''])[0]
                if not url: self._send({'ok':False,'error':'missing url'},400)
                else:
                    obj,code=play(url); self._send(obj,code)
            else: self._send({'ok':False,'error':'not found'},404)
        except Exception as e:
            self._send({'ok':False,'error':type(e).__name__,'message':str(e)},500)
    def log_message(self, fmt, *args): print(fmt%args, flush=True)

if __name__=='__main__':
    print(f'BT sidecar listening on 0.0.0.0:{PORT}, target={ADDR}', flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT), H).serve_forever()
