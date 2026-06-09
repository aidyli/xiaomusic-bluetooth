#!/usr/bin/env python3
import json, os, re, subprocess, time, urllib.parse, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_ADDR=os.environ.get('BT_TARGET_MAC','44:F7:70:81:9C:C4').upper()
PORT=int(os.environ.get('BT_BRIDGE_PORT','58091'))
SINK=os.environ.get('BT_SINK','')
CURRENT_ADDR=os.environ.get('BT_CURRENT_MAC','').upper() or DEFAULT_ADDR
MPV_PROC=None
STATE={'scan': {'running': False, 'last': None}, 'connect': {'running': False, 'last': None}}
LOCK=threading.Lock()
MAC_RE=re.compile(r'^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$')

def normalize_addr(addr):
    addr=(addr or '').strip().upper()
    return addr if MAC_RE.match(addr) else ''

def run(cmd, timeout=20):
    try:
        p=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {'returncode':p.returncode,'stdout':p.stdout[-6000:],'stderr':p.stderr[-6000:]}
    except subprocess.TimeoutExpired as e:
        return {'returncode':124,'stdout':(e.stdout or '')[-6000:] if isinstance(e.stdout,str) else '', 'stderr':((e.stderr or '')[-6000:] if isinstance(e.stderr,str) else '') + ' TIMEOUT'}
    except Exception as e:
        return {'returncode':255,'stdout':'','stderr':f'{type(e).__name__}: {e}'}

def bluez_sink_name(addr):
    addr=normalize_addr(addr)
    return f"bluez_sink.{addr.replace(':','_')}.a2dp_sink" if addr else ''

def get_sink(addr=None):
    global SINK
    addr=normalize_addr(addr) or normalize_addr(CURRENT_ADDR) or normalize_addr(DEFAULT_ADDR)
    if SINK and (not addr or addr.replace(':','_') in SINK or 'bluez' in SINK):
        return SINK
    p=run(['pactl','list','short','sinks'], timeout=5)
    lines=p.get('stdout','').splitlines()
    target=bluez_sink_name(addr)
    if target:
        for line in lines:
            parts=line.split('\t')
            if len(parts)>1 and parts[1] == target:
                SINK=parts[1]
                return SINK
        needle=addr.replace(':','_')
        for line in lines:
            parts=line.split('\t')
            if len(parts)>1 and needle in parts[1] and 'bluez' in parts[1]:
                SINK=parts[1]
                return SINK
    for line in lines:
        parts=line.split('\t')
        if len(parts)>1 and 'bluez' in parts[1]:
            SINK=parts[1]
            return SINK
    return ''

def parse_devices(text):
    devices=[]
    seen=set()
    for line in (text or '').splitlines():
        m=re.search(r'Device\s+([0-9A-Fa-f:]{17})\s*(.*)', line)
        if not m: continue
        addr=m.group(1).upper()
        if addr in seen: continue
        seen.add(addr)
        devices.append({'address':addr,'name':m.group(2).strip() or addr})
    return devices

def all_devices():
    devs=run(['bluetoothctl','devices'],5)
    paired=run(['bluetoothctl','paired-devices'],5)
    devices=parse_devices(devs.get('stdout',''))
    paired_set={d['address'] for d in parse_devices(paired.get('stdout',''))}
    for d in devices:
        info=run(['bluetoothctl','info',d['address']],5)
        out=info.get('stdout','')
        d.update({
            'paired': 'Paired: yes' in out,
            'trusted': 'Trusted: yes' in out,
            'connected': 'Connected: yes' in out,
            'audio_sink': 'Audio Sink' in out or 'Advanced Audio Distribu' in out,
            'info': info,
        })
        if d['address'] in paired_set:
            d['paired']=True
    return devices

def scan_blocking(seconds=30):
    steps=[]
    seconds=max(5, min(180, int(seconds)))
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
    steps.append({'cmd':['timeout',str(seconds),'btmgmt','find'], **run(['timeout',str(seconds),'btmgmt','find'],seconds+5)})
    bredr_cmd='printf "menu scan\ntransport bredr\nback\nscan on\n" | timeout '+str(seconds)+' bluetoothctl'
    steps.append({'cmd':['bash','-lc',bredr_cmd], **run(['bash','-lc',bredr_cmd],seconds+5)})
    steps.append({'cmd':['timeout',str(seconds),'bluetoothctl','scan','on'], **run(['timeout',str(seconds),'bluetoothctl','scan','on'],seconds+5)})
    steps.append({'cmd':['timeout',str(max(8, seconds//2)),'hcitool','scan'], **run(['timeout',str(max(8, seconds//2)),'hcitool','scan'],max(12,seconds//2+5))})
    devices_cmd=run(['bluetoothctl','devices'],5)
    devices=all_devices()
    return {'steps':steps,'devices_cmd':devices_cmd,'devices':devices,'found_count':len(devices),'found':len(devices)>0}

def connect_blocking(scan_if_missing=True, addr=None):
    global CURRENT_ADDR, SINK
    addr=normalize_addr(addr) or normalize_addr(CURRENT_ADDR) or normalize_addr(DEFAULT_ADDR)
    if not addr:
        return {'error':'invalid_address','connected':False}
    out=[]
    info0=run(['bluetoothctl','info',addr], timeout=5)
    out.append({'cmd':['bluetoothctl','info',addr], **info0})
    if scan_if_missing and info0.get('returncode') != 0:
        out.append({'phase':'scan', **scan_blocking(30)})
    for cmd in ([['bluetoothctl','power','on'], ['bluetoothctl','pairable','on'], ['bluetoothctl','agent','NoInputNoOutput'], ['bluetoothctl','default-agent'], ['bluetoothctl','pair',addr], ['bluetoothctl','trust',addr], ['bluetoothctl','connect',addr]]):
        out.append({'cmd':cmd, **run(cmd, timeout=30)})
    time.sleep(3)
    info=run(['bluetoothctl','info',addr],5)
    sinks=run(['pactl','list','short','sinks'],5)
    connected='Connected: yes' in info.get('stdout','')
    if connected:
        CURRENT_ADDR=addr
        SINK=''
    return {'address':addr,'steps':out,'device':info,'sink':get_sink(addr), 'sinks': sinks, 'connected':connected}

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

def play(url, addr=None):
    global MPV_PROC
    stop()
    addr=normalize_addr(addr) or normalize_addr(CURRENT_ADDR) or normalize_addr(DEFAULT_ADDR)
    c=connect_blocking(scan_if_missing=False, addr=addr)
    sink=get_sink(addr)
    if not sink:
        return {'ok':False,'error':'no_bluez_sink','connect':c}, 500
    cmd=['mpv','--no-video','--ao=pulse',f'--audio-device=pulse/{sink}',url]
    MPV_PROC=subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {'ok':True,'action':'play','address':addr,'pid':MPV_PROC.pid,'sink':sink}, 200

def status_obj(addr=None):
    addr=normalize_addr(addr) or normalize_addr(CURRENT_ADDR) or normalize_addr(DEFAULT_ADDR)
    return {'ok':True,'default_address':DEFAULT_ADDR,'current_address':CURRENT_ADDR,'requested_address':addr,'sink':get_sink(addr),'jobs':STATE,'devices':all_devices(),'sinks':run(['pactl','list','short','sinks'],5),'controller':run(['bluetoothctl','show'],5),'device':run(['bluetoothctl','info',addr],5),'processes':run(['bash','-lc','pgrep -af "mpv|bluetoothd|pulseaudio" || true'],5)}

class H(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        data=json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header('content-type','application/json; charset=utf-8'); self.send_header('content-length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); qs=urllib.parse.parse_qs(u.query)
        try:
            addr=normalize_addr(qs.get('address',[''])[0])
            if u.path=='/health': self._send({'ok':True,'sink':get_sink(addr),'default_address':DEFAULT_ADDR,'current_address':CURRENT_ADDR,'scan_running':STATE['scan']['running'],'connect_running':STATE['connect']['running']})
            elif u.path=='/status' or u.path=='/debug': self._send(status_obj(addr))
            elif u.path=='/scan':
                async_mode=qs.get('async',['1'])[0] != '0'
                seconds=int(qs.get('seconds',['30'])[0])
                if async_mode: self._send({'ok':True,'action':'scan',**start_job('scan', lambda: scan_blocking(seconds))})
                else: self._send({'ok':True,'action':'scan', **scan_blocking(seconds)})
            elif u.path=='/connect':
                async_mode=qs.get('async',['1'])[0] != '0'
                if async_mode: self._send({'ok':True,'action':'connect','address':addr or CURRENT_ADDR,**start_job('connect', lambda: connect_blocking(True, addr))})
                else:
                    res=connect_blocking(True, addr)
                    self._send({'ok':res.get('connected',False),'action':'connect',**res})
            elif u.path=='/stop': self._send({'ok':True,'action':'stop',**stop()})
            elif u.path=='/disconnect':
                target=addr or normalize_addr(CURRENT_ADDR) or normalize_addr(DEFAULT_ADDR)
                s=stop(); d=run(['bluetoothctl','disconnect',target],15); self._send({'ok':d['returncode']==0,'action':'disconnect','address':target,'stop':s,'disconnect':d})
            elif u.path=='/play':
                url=qs.get('url',[''])[0]
                if not url: self._send({'ok':False,'error':'missing url'},400)
                else:
                    obj,code=play(url, addr); self._send(obj,code)
            else: self._send({'ok':False,'error':'not found'},404)
        except Exception as e:
            self._send({'ok':False,'error':type(e).__name__,'message':str(e)},500)
    def log_message(self, fmt, *args): print(fmt%args, flush=True)

if __name__=='__main__':
    print(f'BT sidecar listening on 0.0.0.0:{PORT}, default_target={DEFAULT_ADDR}', flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT), H).serve_forever()
