import html, json, os, re, time
from typing import Optional
import aiohttp
from Elevenyts import config
from Elevenyts.helpers._inline import RichMarkup, RichButton

_PLAYER_PHOTOS = {}


def _api(method):
    return f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}"

def _time(sec, duration):
    sec=max(0,int(sec or 0)); return time.strftime('%H:%M:%S' if duration>=3600 else '%M:%S', time.gmtime(sec))

def progress_text(media, timer=None):
    duration=int(getattr(media,'duration_sec',0) or 0)
    if timer: return timer
    if not duration: return 'LIVE'
    played=max(0,min(int(getattr(media,'time',0) or 0),duration)); n=12
    filled=int(round(n*played/duration)); return f"{_time(played,duration)} {'━'*filled}●{'━'*(n-filled)} {_time(duration,duration)}"

def _clean_base_html(base_html):
    text = base_html or ''
    # Player controls are generated centrally by rich_html(). If a caller
    # accidentally passes a text string that already contains controls,
    # remove those rows first so they can never be rendered twice.
    text = re.sub(r'<tg-button-row[^>]*>.*?</tg-button-row>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<a\s+href=([^"\'>\s]+)>', r'<a href="\1">', text)
    text = re.sub(r'</?blockquote(?:\s+[^>]*)?>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text

def _button_html(b):
    text=html.escape(b.text, quote=False)
    if b.callback_data is not None:
        style=f' style="{b.style}"' if b.style else ''
        return f'<tg-button type="callback_data"{style} data="{html.escape(b.callback_data, quote=True)}">{text}</tg-button>'
    if b.url is not None:
        style=f' style="{b.style}"' if b.style else ''
        return f'<tg-button type="url"{style} url="{html.escape(b.url, quote=True)}">{text}</tg-button>'
    if b.copy_text is not None:
        style=f' style="{b.style}"' if b.style else ''
        return f'<tg-button type="copy_text"{style} text="{html.escape(b.copy_text, quote=True)}">{text}</tg-button>'
    return f'<tg-button type="disabled">{text}</tg-button>'

def markup_html(markup):
    if not isinstance(markup, RichMarkup): return ''
    rows=[]
    for row in markup.rows:
        rows.append('<tg-button-row align="center">'+''.join(_button_html(b) for b in row)+'</tg-button-row>')
    return ''.join(rows)

def controls_html(chat_id, media, *, timer=None, playing=True, remove=False):
    if remove: return ''
    state='pause' if playing else 'resume'; label='Ⅱ Pause' if playing else '▶ Resume'
    try:
        # Lazy import avoids a circular import during Elevenyts package startup.
        from Elevenyts import queue
        upcoming=max(0,len(queue.get_queue(chat_id))-1)
    except Exception:
        upcoming=0
    if playing: phase=int(time.time()//5)%3
    else: phase=0
    palettes=(('success','primary','danger','success'),('primary','danger','success','primary'),('danger','success','primary','danger'))
    time_style,replay_style,state_style,queue_style=palettes[phase]
    p=html.escape(progress_text(media,timer))
    return (
        f'<tg-button-row align="center"><tg-button type="callback_data" style="{time_style}" data="controls status {chat_id}">{p}</tg-button></tg-button-row>'
        f'<tg-button-row align="center"><tg-button type="callback_data" style="{replay_style}" data="controls replay {chat_id}">↻ Replay</tg-button>'
        f'<tg-button type="callback_data" style="{state_style}" data="controls {state} {chat_id}">{label}</tg-button>'
        f'<tg-button type="callback_data" style="{queue_style}" data="controls skip {chat_id}">» Skip</tg-button></tg-button-row>'
        f'<tg-button-row align="center"><tg-button type="callback_data" style="{time_style}" data="controls queue {chat_id}">≡ Queue · {upcoming}</tg-button></tg-button-row>'
    )

def rich_html(base_html, chat_id=None, media=None, *, timer=None, playing=True, remove=False, markup=None):
    clean=_clean_base_html(base_html)
    if remove: return clean
    if markup is not None: return clean+'\n\n'+markup_html(markup)
    return clean+'\n\n'+controls_html(chat_id,media,timer=timer,playing=playing)

async def _request(method,data,file_path=None):
    timeout=aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if file_path and os.path.isfile(str(file_path)):
            form=aiohttp.FormData()
            for k,v in data.items(): form.add_field(k,json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else str(v))
            with open(file_path,'rb') as fp:
                form.add_field('player_cover',fp,filename=os.path.basename(str(file_path)),content_type='image/jpeg')
                async with session.post(_api(method),data=form) as r: result=await r.json(content_type=None)
        else:
            async with session.post(_api(method),json=data) as r: result=await r.json(content_type=None)
    if not result.get('ok'): raise RuntimeError(result.get('description',f'Telegram {method} failed'))
    return result

def _photo_id_from_message(msg):
    try:
        photo = getattr(msg, 'photo', None)
        if photo and getattr(photo, 'file_id', None):
            return photo.file_id
        if isinstance(photo, (list, tuple)) and photo:
            return photo[-1].file_id
    except Exception:
        pass
    return None

def _response_photo_id(obj):
    if isinstance(obj,dict):
        for key in ('photo','photos'):
            val=obj.get(key)
            if isinstance(val,list):
                for x in reversed(val):
                    if isinstance(x,dict) and x.get('file_id'): return x['file_id']
            if isinstance(val,dict) and val.get('file_id'): return val['file_id']
        for v in obj.values():
            x=_response_photo_id(v)
            if x:return x
    elif isinstance(obj,list):
        for v in reversed(obj):
            x=_response_photo_id(v)
            if x:return x
    return None

async def _send_rich_payload(chat_id, rich, *, photo=None, reply_to_message_id=None):
    """Send an already-built Rich Message without adding player controls."""
    file_path = None
    if photo and os.path.isfile(str(photo)):
        file_path = str(photo)
        rich = dict(rich)
        rich['html'] = f'<img src="tg://photo?id=rich_cover"/>\n{rich.get("html", "")}'
        rich['media'] = [{
            'id': 'rich_cover',
            'media': {'type': 'photo', 'media': 'attach://player_cover'},
        }]
    elif photo:
        rich = dict(rich)
        rich['html'] = f'<img src="tg://photo?id=rich_cover"/>\n{rich.get("html", "")}'
        rich['media'] = [{
            'id': 'rich_cover',
            'media': {'type': 'photo', 'media': str(photo)},
        }]

    data = {'chat_id': chat_id, 'rich_message': rich}
    if reply_to_message_id:
        data['reply_parameters'] = {'message_id': int(reply_to_message_id)}

    result = await _request('sendRichMessage', data, file_path)
    msg = result['result']
    mid = int(msg['message_id'])
    pid = _response_photo_id(msg)
    if pid:
        _PLAYER_PHOTOS[(int(chat_id), mid)] = pid
    return mid


async def send_rich_message(chat_id, text, markup=None, *, photo=None, reply_to_message_id=None, quote=True):
    """Send a generic Rich Message.

    This function deliberately does NOT add music-player controls. Player
    controls are added only by send_player()/edit_player(). This prevents
    duplicate controls and prevents callbacks containing chat_id=None.
    """
    body = rich_html(text, markup=markup) if markup is not None else _clean_base_html(text)
    return await _send_rich_payload(
        chat_id,
        {'html': body},
        photo=photo,
        reply_to_message_id=reply_to_message_id,
    )


async def send_player(chat_id, *args, **kwargs):
    """Compatibility sender for all existing player call signatures.

    Accepts the historical positional forms without falling back to the
    classic keyboard.  The player message is still rendered exactly once
    as a Rich Message.
    """
    reply_to_message_id = kwargs.pop("reply_to_message_id", None)
    text = kwargs.pop("text", None)
    photo = kwargs.pop("photo", None)
    media = kwargs.pop("media", None)
    playing = kwargs.pop("playing", True)

    # Accept up to four legacy positional values after chat_id.
    vals = list(args[:4])
    if vals and text is None:
        text = vals.pop(0)
    if vals:
        # Older integrations used either (text, photo, media) or
        # (text, media, photo). Detect media objects by their duration/title.
        candidate = vals.pop(0)
        if media is None and (hasattr(candidate, "duration_sec") or hasattr(candidate, "title")):
            media = candidate
        elif photo is None:
            photo = candidate
    if vals:
        candidate = vals.pop(0)
        if media is None and (hasattr(candidate, "duration_sec") or hasattr(candidate, "title")):
            media = candidate
        elif photo is None:
            photo = candidate
        elif reply_to_message_id is None:
            reply_to_message_id = getattr(candidate, "id", candidate)
    if vals:
        candidate = vals.pop(0)
        if isinstance(candidate, bool):
            playing = candidate
        elif reply_to_message_id is None:
            reply_to_message_id = getattr(candidate, "id", candidate)

    if text is None and media is not None:
        title = getattr(media, "title", "Now Playing")
        text = f"<b>{html.escape(str(title))}</b>"
    if text is None:
        text = ""

    # Recover a cover from the media object when the caller omitted photo.
    if photo is None and media is not None:
        for attr in ("thumbnail", "thumb", "photo", "cover", "cover_path"):
            value = getattr(media, attr, None)
            if value:
                photo = value
                break

    mid = await _send_rich_payload(
        chat_id,
        {"html": rich_html(text, chat_id=chat_id, media=media, playing=playing)},
        photo=photo,
        reply_to_message_id=reply_to_message_id,
    )
    if media is not None:
        try:
            media.message_id = mid
        except Exception:
            pass
    return mid


async def edit_rich_message(message_or_chat_id, text, markup=None, *, message_id=None, photo_file_id=None):
    if hasattr(message_or_chat_id,'chat'):
        msg=message_or_chat_id; chat_id=msg.chat.id; message_id=msg.id
        photo_file_id=photo_file_id or _photo_id_from_message(msg) or _PLAYER_PHOTOS.get((chat_id,message_id))
    else:
        chat_id=int(message_or_chat_id); message_id=int(message_id)
        photo_file_id=photo_file_id or _PLAYER_PHOTOS.get((chat_id,message_id))
    body=rich_html(text,markup=markup)
    rich={'html':body}
    if photo_file_id:
        rich['html']=f'<img src="tg://photo?id=rich_cover"/>\n{body}'; rich['media']=[{'id':'rich_cover','media':{'type':'photo','media':photo_file_id}}]
    try:
        await _request('editMessageText',{'chat_id':chat_id,'message_id':message_id,'rich_message':rich})
        if photo_file_id: _PLAYER_PHOTOS[(chat_id,message_id)]=photo_file_id
        return True
    except Exception:
        return False

async def edit_player(chat_id,message_id,base_html,media,*,timer=None,playing=True,remove=False):
    if remove:
        try: await _request('deleteMessage',{'chat_id':chat_id,'message_id':message_id}); _PLAYER_PHOTOS.pop((chat_id,message_id),None); return True
        except Exception:return False
    photo=_PLAYER_PHOTOS.get((chat_id,message_id))
    rich={'html':rich_html(base_html,chat_id,media,timer=timer,playing=playing)}
    if photo:
        rich['html']=f'<img src="tg://photo?id=player_cover"/>\n{rich["html"]}'; rich['media']=[{'id':'player_cover','media':{'type':'photo','media':photo}}]
    try:
        await _request('editMessageText',{'chat_id':chat_id,'message_id':message_id,'rich_message':rich}); return True
    except Exception:return False

async def edit_player_message(chat_id,message_id,base_html,media,*args,**kwargs):
    return await edit_player(chat_id,message_id,base_html,media,timer=kwargs.get('timer'),playing=kwargs.get('playing',True),remove=kwargs.get('remove',False))
