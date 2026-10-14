"""Render a 10-second promo using existing Verif.AI screen captures and local tools."""
from pathlib import Path
import math, subprocess, wave, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
W,H,FPS,DURATION = 1080,1920,30,10
NAVY='#082452'; BLUE='#0b3d91'; RED='#d7263d'; GOLD='#f4b400'
WHITE='#f8fafc'; SOFT='#bacbe3'
SCREEN=Image.open(ROOT/'verifai-frontend/public/images/news-analyzer-preview.png').convert('RGB')
INPUT=SCREEN.crop((9,93,405,574))
RESULT=SCREEN.crop((423,93,1017,588))
FONTS={}
def font(size,bold=False):
    key=(size,bold)
    if key not in FONTS: FONTS[key]=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size)
    return FONTS[key]
def txt(im,xy,s,size=36,fill=WHITE,bold=False):
    ImageDraw.Draw(im).text(xy,s,font=font(size,bold),fill=fill,stroke_width=0)
def ease(x):
    x=min(1,max(0,x)); return 1-(1-x)**3
def logo(im,x,y,size=72):
    d=ImageDraw.Draw(im); k=size/80
    def points(seq): return [(x+a*k,y+b*k) for a,b in seq]
    for seq,col in [([(5,25),(5,5),(26,5)],BLUE), ([(5,56),(5,75),(26,75)],BLUE), ([(54,5),(75,5),(75,25)],RED), ([(75,56),(75,75),(54,75)],RED)]:
        d.line(points(seq),fill=col,width=max(2,round(5*k)),joint='curve')
    d.polygon(points([(16,26),(40,61),(64,26),(51,26),(40,42),(29,26)]),fill=NAVY)
    for a in [-40,-20,0,20,40]:
        r=math.radians(a); d.line(points([(40+math.sin(r)*9,29-math.cos(r)*9),(40+math.sin(r)*22,29-math.cos(r)*22)]),fill=GOLD,width=max(2,round(2*k)))
    for a,b in [(17,48),(63,48),(40,69)]:
        p=[]
        for i in range(10):
            ang=-math.pi/2+i*math.pi/5; rr=5 if i%2==0 else 2
            p.append((a+math.cos(ang)*rr,b+math.sin(ang)*rr))
        d.polygon(points(p),fill=GOLD)
def brand(im,x=86,y=126,big=False):
    d=ImageDraw.Draw(im); sz=96 if big else 68
    d.rounded_rectangle((x,y,x+sz+16,y+sz+16),radius=12,fill=WHITE)
    logo(im,x+8,y+8,sz)
    txt(im,(x+sz+36,y-2),'Verif.AI',78 if big else 54,bold=True)
def base(t):
    im=Image.new('RGB',(W,H),NAVY);d=ImageDraw.Draw(im)
    # Quiet ruled geometry borrowed from the app's landing page.
    for y in range(340,1820,180):d.line((86,y,994,y),fill='#13325e',width=1)
    d.line((994,120,994,1770),fill='#24426b',width=1)
    d.rectangle((86,1795,994,1798),fill='#28466e')
    d.rectangle((86,1795,86+908*t/10,1798),fill=GOLD)
    txt(im,(86,1820),'READ. CHECK. VERIFY.',25,SOFT,True)
    txt(im,(900,1820),f'{min(10,int(t)+1):02d}/10',25,SOFT)
    return im
def label(im,n,word):
    d=ImageDraw.Draw(im);d.rounded_rectangle((86,275,146,335),radius=10,fill=RED)
    txt(im,(102,281),n,32,bold=True);txt(im,(169,282),word,31,GOLD,True)
def card(im,asset,x,y,width):
    height=round(asset.height*width/asset.width)
    resized=asset.resize((width,height),Image.Resampling.LANCZOS)
    mask=Image.new('L',(width,height),0);ImageDraw.Draw(mask).rounded_rectangle((0,0,width-1,height-1),radius=18,fill=255)
    im.paste(resized,(x,y),mask)
    return height
def pointer(im,x,y,click=False):
    d=ImageDraw.Draw(im)
    if click:
        d.ellipse((x-32,y-32,x+32,y+32),outline=GOLD,width=6)
    d.polygon([(x,y),(x+5,y+51),(x+18,y+37),(x+30,y+59),(x+42,y+52),(x+28,y+30),(x+48,y+25)],fill=NAVY,outline='white',width=3)
def scene(t):
    im=base(t);d=ImageDraw.Draw(im)
    if t<2:
        brand(im)
        txt(im,(86,332),'A SECOND LOOK MATTERS.',29,GOLD,True)
        shift=int(35*(1-ease(t/.6)))
        for y,s in [(445,'Before you'),(568,'share,'),(691,'verify.')]:txt(im,(80,y+shift),s,108,GOLD if s=='verify.' else WHITE,True)
        txt(im,(86,935),'Your content-checking workspace.',38,SOFT)
        for i,(n,title,sub) in enumerate([('01','Text','Examine writing patterns'),('02','News','Compare claims with sources'),('03','Images','Inspect visual signals')]):
            yy=1110+i*158
            d.line((86,yy-24,938,yy-24),fill='#345176',width=2)
            txt(im,(88,yy+5),n,27,GOLD,True);txt(im,(164,yy-8),title,44,bold=True);txt(im,(164,yy+53),sub,30,SOFT)
        txt(im,(86,1640),'English · Filipino · Taglish',31,SOFT)
    elif t<5:
        brand(im);label(im,'1','CHECK A CLAIM')
        txt(im,(82,374),'Paste. Then check.',75,bold=True)
        txt(im,(86,484),'Start with a headline or story.',35,SOFT)
        cy=600+int(35*(1-ease((t-2)/.35)))
        ch=card(im,INPUT,86,cy,908)
        # Match the button location in the source capture; cursor movement is editorial.
        p=ease((t-2.7)/1.0);cx=int(790+(710-790)*p); yy=int(cy+590+(1020-590)*p)
        pointer(im,cx,yy,3.85<t<4.2)
        txt(im,(86,1725),'RECORDED EXAMPLE · TIME COMPRESSED',23,SOFT,True)
    elif t<8:
        brand(im);label(im,'2','REVIEW THE RESULT')
        txt(im,(82,374),'Read the evidence.',73,bold=True)
        txt(im,(86,482),'See the explanation and source links.',34,SOFT)
        cy=610+int(30*(1-ease((t-5)/.35)))
        card(im,RESULT,86,cy,908)
        # Highlight existing source links; never manufacture new results.
        if t>5.65:
            d.rounded_rectangle((111,cy+499,967,cy+727),radius=10,outline=GOLD,width=4)
        txt(im,(86,1450),'Context comes first.',52,bold=True)
        txt(im,(86,1532),'Open the sources. Make an informed call.',33,SOFT)
        txt(im,(86,1725),'RECORDED EXAMPLE · RESULTS CAN VARY',23,SOFT,True)
    else:
        brand(im,86,310,True)
        txt(im,(86,570),'BEFORE YOU SHARE,',32,GOLD,True)
        txt(im,(78,655),'Verify.',148,bold=True)
        txt(im,(86,898),'Text. News. Images.',48,SOFT)
        d.rounded_rectangle((86,1080,994,1220),radius=14,fill=RED)
        txt(im,(144,1108),'Try Verif.AI',65,bold=True)
        d.line((845,1150,925,1150),fill=WHITE,width=5)
        d.line((900,1125,925,1150,900,1175),fill=WHITE,width=5)
        txt(im,(86,1370),'Read. Check. Verify.',42,GOLD,True)
        txt(im,(86,1460),'A little more context.',36,SOFT)
        txt(im,(86,1510),'A more informed decision.',36,SOFT)
    return im
def frame(t):
    im=scene(t)
    for cut in [2,5,8]:
        if cut<=t<cut+.16:
            old=scene(cut-.001); im=Image.blend(old,im,ease((t-cut)/.16))
    return im

def audio():
    sr=48000;t=np.arange(sr*DURATION)/sr; a=np.zeros(len(t))
    # Original synthesized soundtrack: soft C-major pulses, no licensed samples.
    for beat in np.arange(0,10,.5):
        dt=t-beat; env=np.exp(-np.maximum(dt,0)*13)*(dt>=0)
        a+=.028*np.sin(2*np.pi*65.406*dt)*env
    for j,start in enumerate([0,2.5,5,7.5]):
        dt=t-start;active=(dt>=0)&(dt<2.5);env=np.minimum(np.maximum(dt,0)/.15,1)*np.maximum(0,1-np.maximum(dt,0)/2.5)**2*active
        for hz in [[261.63,329.63,392],[220,261.63,329.63],[174.61,261.63,349.23],[196,293.66,392]][j]:a+=.009*np.sin(2*np.pi*hz*t)*env
    for start in [2,5,8]:
        dt=t-start;env=np.exp(-np.maximum(dt,0)*32)*(dt>=0)
        a+=.023*np.sin(2*np.pi*(880*dt-200*dt*dt))*env
    a*=np.minimum(t/.08,1)*np.minimum((10-t)/.4,1)
    with wave.open(str(HERE/'music.wav'),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((a*32767).astype('<i2').tobytes())

if __name__=='__main__':
    audio()
    with wave.open(str(HERE/'voice-original.wav')) as f: voice_duration=f.getnframes()/f.getframerate()
    speed=max(1,voice_duration/9.3)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    cmd=[ffmpeg,'-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
         '-i',str(HERE/'voice-original.wav'),'-i',str(HERE/'music.wav'),
         '-filter_complex',f'[1:a]atempo={speed:.6f},volume=1.3,adelay=180|180,apad[v];[2:a]volume=0.8[m];[v][m]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]',
         '-map','0:v','-map','[a]','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t','10','-movflags','+faststart',str(HERE/'verifai-promo-10s.mp4')]
    with open(HERE/'render.log','w') as log:
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
        for i in range(FPS*DURATION):
            p.stdin.write(frame(i/FPS).tobytes())
            if i%60==0:print(f'Rendered {i}/{FPS*DURATION}',flush=True)
        p.stdin.close();code=p.wait()
    if code:raise RuntimeError((HERE/'render.log').read_text()[-3000:])
    frame(.9).save(HERE/'poster.jpg',quality=95)
    sheet=Image.new('RGB',(1440,1280),'#dce3ee')
    for i,tm in enumerate([.8,2.6,4.1,5.7,7.3,8.8]):
        small=frame(tm).resize((360,640),Image.Resampling.LANCZOS)
        sheet.paste(small,((i%4)*360,(i//4)*640))
    sheet.save(HERE/'review-contact-sheet.jpg',quality=95)
    (HERE/'render-metadata.json').write_text(json.dumps({'duration_seconds':10,'dimensions':[W,H],'fps':FPS,'voice_source':'Windows Microsoft Zira Desktop','voice_original_duration':voice_duration,'voice_speed':speed,'source_screenshot':str(ROOT/'verifai-frontend/public/images/news-analyzer-preview.png')},indent=2))
    print('Done:',HERE/'verifai-promo-10s.mp4',flush=True)
