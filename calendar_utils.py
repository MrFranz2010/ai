"""Pure Google Calendar event helpers and iCalendar serialization."""

import datetime
import re


GOOGLE_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def google_schema_value(schema):
    """Convert a tool parameter schema to the Gemini declaration format."""
    converted = {}
    for key, value in schema.items():
        if key == "type":
            if isinstance(value, list):
                types = [item for item in value if item != "null"]
                if "null" in value:
                    converted["nullable"] = True
                converted["type"] = types[0].upper() if types else "STRING"
            else:
                converted["type"] = value.upper()
        elif key == "properties":
            converted[key] = {
                name: google_schema_value(property_schema)
                for name, property_schema in value.items()
            }
        elif key == "items":
            converted[key] = google_schema_value(value)
        else:
            converted[key] = value
    return converted


def google_parse_datetime(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Indica {field} nel formato YYYY-MM-DDTHH:MM.")
    clean = value.strip()
    try:
        if GOOGLE_DATETIME_PATTERN.fullmatch(clean):
            parsed = datetime.datetime.strptime(clean, "%Y-%m-%dT%H:%M")
        else:
            parsed = datetime.datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"{field} non è una data valida: usa YYYY-MM-DDTHH:MM."
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def google_event(event, calendar_id):
    if not isinstance(event, dict):
        raise RuntimeError("Google Calendar ha restituito un evento non valido.")
    start = event.get("start") if isinstance(event.get("start"), dict) else {}
    end = event.get("end") if isinstance(event.get("end"), dict) else {}
    return {
        "id": event.get("id"),
        "title": event.get("summary") or "(senza titolo)",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "location": event.get("location") or "",
        "description": event.get("description") or "",
        "html_link": event.get("htmlLink") or "",
        "calendar": calendar_id,
    }


def ics_escape(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def build_calendar_ics(events, tasks):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NOKK//Assistente AI//IT",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:NOKK",
    ]
    for event in events:
        start = datetime.datetime.strptime(event["starts_at"], "%Y-%m-%dT%H:%M")
        end = start + datetime.timedelta(hours=1)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event['id']}@nokk",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{ics_escape(event['title'])}",
        ])
        if event.get("description"):
            lines.append(f"DESCRIPTION:{ics_escape(event['description'])}")
        lines.append("END:VEVENT")
    for task in tasks:
        lines.extend([
            "BEGIN:VTODO",
            f"UID:{task['id']}@nokk",
            f"DTSTAMP:{stamp}",
            f"SUMMARY:{ics_escape(task['title'])}",
        ])
        if task.get("due_date"):
            lines.append(f"DUE;VALUE=DATE:{task['due_date'].replace('-', '')}")
        if task.get("completed"):
            lines.extend(["STATUS:COMPLETED", f"COMPLETED:{stamp}"])
        lines.append("END:VTODO")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
