"""Turn a short Italian sentence into a planner reminder.

The web composer and the assistant share this module so that «domani alle 10»
means the same thing everywhere, and the lead-time reminders use the stored
``starts_at`` instead of a second source of truth.
"""

import datetime
import re

REMINDER_USAGE = (
    "Indica quando: «domani alle 10», «venerdì alle 9», «il 20 alle 18:30»."
)
REMINDER_LEAD_MINUTES = 30
MAX_REMINDER_TITLE_LENGTH = 200

MONTHS = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
)
WEEKDAYS = (
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
)
MONTH_INDEX = {name: index + 1 for index, name in enumerate(MONTHS)}

_FILLER = re.compile(
    r"(?i)^\s*(?:/promemoria|promemoria|ricordami(?:\s+di|\s+che)?|"
    r"ricorda(?:mi)?(?:\s+di)?)\s*[:\-–]?\s*"
)
_TIME = re.compile(
    r"(?i)\b(?:alle|ore|h)\s*(\d{1,2})(?::(\d{1,2}))?\b|"
    r"\b(\d{1,2}):(\d{2})\b"
)
_WEEKDAY = re.compile(
    r"(?i)\b(luned[ìi]|marted[ìi]|mercoled[ìi]|gioved[ìi]|venerd[ìi]|"
    r"sabato|domenica)\b"
)
_RELATIVE_HOURS = re.compile(
    r"(?i)\b(?:tra|fra)\s+(\d{1,2})\s+(?:ora|ore)\b"
)
_RELATIVE_DAYS = re.compile(
    r"(?i)\b(?:tra|fra)\s+(\d{1,2})\s+(giorno|giorni|settimana|settimane)\b"
)
_DAY_OF_MONTH = re.compile(
    r"(?i)\bil\s+(\d{1,2})(?:\s*/\s*(\d{1,2}))?\b"
)
_DAY_WITH_MONTH = re.compile(
    r"(?i)\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b"
)


def _clean_title(text):
    title = re.sub(r"\s+", " ", text).strip(" ,.;:-–")
    title = re.sub(r"(?i)^(?:di|che|per)\s+", "", title)
    if len(title) > MAX_REMINDER_TITLE_LENGTH:
        title = title[:MAX_REMINDER_TITLE_LENGTH].rstrip()
    return title or "Promemoria"


def _date_label(day, now):
    days = (day - now.date()).days
    if days == 0:
        return "oggi"
    if days == 1:
        return "domani"
    if days == 2:
        return "dopodomani"
    if 0 < days <= 6:
        return WEEKDAYS[day.weekday()]
    return f"{day.day} {MONTHS[day.month - 1]}"


def _next_weekday(now, target, has_time, hour, minute):
    """Nearest matching weekday; today only counts when the time is later."""
    for offset in range(0, 8):
        day = now.date() + datetime.timedelta(days=offset)
        if day.weekday() != target:
            continue
        if offset == 0 and has_time:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                continue
        return day
    return now.date() + datetime.timedelta(days=7)


def parse_reminder(text, now):
    """Parse «Riunione domani alle 10» into a planner task draft.

    Returns a dict with ``title``, ``starts_at`` (``YYYY-MM-DDTHH:MM`` or None),
    ``due_date`` (``YYYY-MM-DD`` or None) and a human ``label``.
    """
    if not isinstance(text, str):
        raise ValueError(REMINDER_USAGE)
    body = _FILLER.sub("", " ".join(text.split()))
    if not body:
        raise ValueError(REMINDER_USAGE)
    working = body

    hour = minute = None
    match = _TIME.search(working)
    if match:
        raw_hour = match.group(1) if match.group(1) is not None else match.group(3)
        raw_minute = match.group(2) if match.group(1) is not None else match.group(4)
        hour = int(raw_hour)
        minute = int(raw_minute) if raw_minute is not None else 0
        if hour > 23 or minute > 59:
            raise ValueError(
                "Orario non valido: usa un'ora tra 0 e 23 e minuti tra 0 e 59."
            )
        working = f"{working[:match.start()]} {working[match.end():]}"

    in_hours = _RELATIVE_HOURS.search(working)
    if in_hours:
        working = f"{working[:in_hours.start()]} {working[in_hours.end():]}"
        moment = (now + datetime.timedelta(hours=int(in_hours.group(1)))).replace(
            second=0, microsecond=0
        )
        return {
            "title": _clean_title(working),
            "starts_at": moment.strftime("%Y-%m-%dT%H:%M"),
            "due_date": moment.date().isoformat(),
            "label": (
                f"tra {int(in_hours.group(1))} ore "
                f"({_date_label(moment.date(), now)} alle {moment.strftime('%H:%M')})"
            ),
        }

    day = None
    relative_days = _RELATIVE_DAYS.search(working)
    if relative_days:
        working = f"{working[:relative_days.start()]} {working[relative_days.end():]}"
        amount = int(relative_days.group(1))
        unit = relative_days.group(2).lower()
        if unit.startswith("settiman"):
            amount *= 7
        day = now.date() + datetime.timedelta(days=amount)
    elif re.search(r"(?i)\bdopodomani\b", working):
        working = re.sub(r"(?i)\bdopodomani\b", " ", working, count=1)
        day = now.date() + datetime.timedelta(days=2)
    elif re.search(r"(?i)\bdomani\b", working):
        working = re.sub(r"(?i)\bdomani\b", " ", working, count=1)
        day = now.date() + datetime.timedelta(days=1)
    elif re.search(r"(?i)\boggi\b", working):
        working = re.sub(r"(?i)\boggi\b", " ", working, count=1)
        day = now.date()
    else:
        weekday = _WEEKDAY.search(working)
        if weekday:
            name = weekday.group(1).lower()
            target = next(
                index for index, label in enumerate(WEEKDAYS)
                if label.startswith(name[:4])
            )
            day = _next_weekday(now, target, hour is not None, hour or 0, minute or 0)
            working = f"{working[:weekday.start()]} {working[weekday.end():]}"
        else:
            with_month = _DAY_WITH_MONTH.search(working)
            if with_month:
                day = datetime.date(
                    now.year,
                    MONTH_INDEX[with_month.group(2).lower()],
                    int(with_month.group(1)),
                )
                if day < now.date():
                    day = day.replace(year=now.year + 1)
                working = f"{working[:with_month.start()]} {working[with_month.end():]}"
            else:
                day_of_month = _DAY_OF_MONTH.search(working)
                if day_of_month:
                    day_number = int(day_of_month.group(1))
                    month = (
                        int(day_of_month.group(2))
                        if day_of_month.group(2)
                        else now.month
                    )
                    if not 1 <= day_number <= 31 or not 1 <= month <= 12:
                        raise ValueError("Data non valida.")
                    try:
                        day = datetime.date(now.year, month, day_number)
                    except ValueError:
                        raise ValueError("Data non valida.") from None
                    if day < now.date():
                        year = now.year + 1
                        day = datetime.date(year, month, day_number)
                    working = (
                        f"{working[:day_of_month.start()]} "
                        f"{working[day_of_month.end():]}"
                    )

    if day is None and hour is None:
        raise ValueError(REMINDER_USAGE)
    if day is None:
        day = now.date()
        if now.replace(hour=hour, minute=minute, second=0, microsecond=0) <= now:
            day = day + datetime.timedelta(days=1)

    title = _clean_title(working)
    label = _date_label(day, now)
    if hour is None:
        return {
            "title": title,
            "starts_at": None,
            "due_date": day.isoformat(),
            "label": label,
        }
    clock = f"{hour:02d}:{minute:02d}"
    return {
        "title": title,
        "starts_at": f"{day.isoformat()}T{clock}",
        "due_date": day.isoformat(),
        "label": f"{label} alle {clock}",
    }


def build_due_soon_reminders(now, tasks, lead_minutes=REMINDER_LEAD_MINUTES):
    """Reminders for tasks starting within the next ``lead_minutes`` minutes."""
    reminders = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("completed"):
            continue
        starts_at = task.get("starts_at")
        if not starts_at:
            continue
        try:
            moment = datetime.datetime.fromisoformat(str(starts_at))
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=now.tzinfo)
        seconds = (moment - now).total_seconds()
        if seconds <= 0 or seconds > lead_minutes * 60:
            continue
        title = " ".join(str(task.get("title") or "").split()) or "Attività"
        minutes = max(1, int(round(seconds / 60)))
        reminders.append({
            "id": task.get("id"),
            "key": f"soon:{task.get('id')}:{starts_at}",
            "message": (
                f"⏰ Tra {minutes} minuti: «{title}» "
                f"({moment.strftime('%H:%M')})."
            ),
        })
    reminders.sort(key=lambda item: item["key"])
    return reminders
