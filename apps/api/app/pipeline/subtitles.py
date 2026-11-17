from app.pipeline.words import Word

ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def ass_color(hex_color: str) -> str:
    cleaned = hex_color.removeprefix("#")
    if len(cleaned) != 6:
        cleaned = "FFFFFF"
    red, green, blue = cleaned[0:2], cleaned[2:4], cleaned[4:6]
    return f"&H00{blue}{green}{red}&".upper()


def format_ass_time(seconds: float) -> str:
    clamped = max(0.0, seconds)
    hours = int(clamped // 3600)
    minutes = int((clamped % 3600) // 60)
    whole = int(clamped % 60)
    centiseconds = int(round((clamped - int(clamped)) * 100))
    if centiseconds == 100:
        whole += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def build_ass(
    words: list[Word],
    *,
    font_name: str,
    font_size: int,
    primary_color: str,
    highlight_color: str,
    position: str,
    clip_start: float = 0.0,
    hook: str = "",
    duration: float = 0.0,
) -> str:
    alignment = ALIGN.get(position, 2)
    primary = ass_color(primary_color)
    highlight = ass_color(highlight_color)
    header = "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{font_size},{primary},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,0,{alignment},80,80,480,1",
            f"Style: Hook,{font_name},58,&H00000000,&H000000FF,&H00000000,&H00FFFFFF&,-1,0,0,0,100,100,0,0,3,18,0,5,80,80,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
    )
    events = [_event(words, index, highlight, primary, clip_start) for index in range(len(words))]
    title = hook.strip()
    if title and duration > 0:
        events.insert(
            0,
            f"Dialogue: 1,{format_ass_time(0)},{format_ass_time(duration)},Hook,,0,0,0,,{{\\an5\\pos(540,980)}}{_escape(title)}",
        )
    return header + "\n" + "\n".join(events) + ("\n" if events else "")


def _event(words: list[Word], index: int, highlight: str, primary: str, clip_start: float) -> str:
    parts: list[str] = []
    first = max(0, index - 1)
    last = min(len(words), index + 2)
    for position in range(first, last):
        word = words[position]
        active = position == index
        color = highlight if active else primary
        effect = f"\\c{color}\\fscx112\\fscy112" if active else f"\\c{color}"
        parts.append("{" + effect + "}" + _escape(word.word.strip()))
    start = format_ass_time(words[index].start - clip_start)
    end = format_ass_time(words[index].end - clip_start)
    return f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{\\an5\\pos(540,1240)}}{' '.join(parts)}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
