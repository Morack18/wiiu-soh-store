"""Generate a tiny syntactically valid WUHB for unit tests; no real game code."""
import gzip
import struct

EMPTY=0xffffffff

def a4(n): return (n+3)&~3
def a16(n): return (n+15)&~15

def make_fake_wuhb():
    tga=struct.pack('<BBBHHBHHHHBB',0,0,2,0,0,0,0,0,128,128,32,0x28)+bytes([0,0,255,255])*(128*128)
    files = [
        ('meta','iconTex.tga.gz',gzip.compress(tga,mtime=0)),
        ('meta','meta.ini',b'[menu]\nlongname=Original\nshortname=Original\nauthor=Upstream\n'),
        ('code','root.rpx',b'FAKE RPX' * 2048),
        ('content','preserve.bin',b'Important content file'),
    ]
    dirs=[('',0),('meta',0),('code',0),('content',0)]
    offsets={}
    cur=0
    for name,_ in dirs:
        offsets[name]=cur
        cur+=24+a4(len(name))
    dir_len=cur
    file_offsets=[]
    part=bytearray()
    cur=0
    for parent,name,data in files:
        file_offsets.append((cur,len(part),data))
        cur+=32+a4(len(name))
        part.extend(b'\0'*(a16(len(part))-len(part)))
        file_offsets[-1]=(file_offsets[-1][0],len(part),data)
        part.extend(data)
    dtable=bytearray(dir_len)
    for i,(name,_p) in enumerate(dirs):
        at=offsets[name]
        nextsib=offsets[dirs[i+1][0]] if i in (1,2) else EMPTY
        child=offsets['meta'] if i==0 else EMPTY
        startfile={'meta':file_offsets[0][0], 'code':file_offsets[2][0], 'content':file_offsets[3][0]}.get(name,EMPTY)
        struct.pack_into('>6I',dtable,at,0 if i else 0, nextsib, child,startfile,EMPTY,len(name))
        dtable[at+24:at+24+len(name)]=name.encode()
    ftable=bytearray(cur)
    for i,(parent,name,data) in enumerate(files):
        at, foffset,_=file_offsets[i]
        sibling = file_offsets[i+1][0] if i==0 else EMPTY
        struct.pack_into('>IIQQII',ftable,at, offsets[parent],sibling,foffset,len(data),EMPTY,len(name))
        ftable[at+32:at+32+len(name)]=name.encode()
    part.extend(b'\0'*(a4(len(part))-len(part)))
    dh_off=0x200+len(part)
    dh=bytes([255])*12
    dt_off=dh_off+len(dh)
    fh=bytes([255])*12
    fh_off=dt_off+len(dtable)
    ft_off=fh_off+len(fh)
    header=struct.pack('>4sI9Q',b'WUHB',80,dh_off,len(dh),dt_off,len(dtable),fh_off,len(fh),ft_off,len(ftable),0x200)
    return header + bytes(0x200-len(header)) + bytes(part) + dh + dtable + fh + ftable
