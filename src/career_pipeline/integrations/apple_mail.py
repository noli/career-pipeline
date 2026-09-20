"""
career_pipeline.integrations.apple_mail - macOS Apple Mail Bridge
Guarded with platform check to ensure zero failure on Windows / Linux.
"""
import sys
import subprocess
from pathlib import Path

def is_apple_mail_supported() -> bool:
    return sys.platform == "darwin"

def export_apple_mail_alerts(inbox_dir: Path, days: int = 14, max_messages: int = 50) -> int:
    """Uses AppleScript to query Apple Mail and export matching alert emails (macOS only)."""
    if not is_apple_mail_supported():
        print("Note: Apple Mail synchronization is only supported on macOS.")
        return 0

    inbox_dir.mkdir(parents=True, exist_ok=True)
    inbox_posix = str(inbox_dir.resolve()).replace("\\", "/") + "/"

    applescript = f"""
    set inboxPath to "{inbox_posix}"
    set msgList to {{}}
    
    tell application "Mail"
        repeat with acc in accounts
            try
                set inb to mailbox "INBOX" of acc
                set msgs to (messages of inb whose (sender contains "linkedin") or (sender contains "stepstone") or (sender contains "indeed") or (sender contains "xing") or (subject contains "Job Alert") or (subject contains "Stellenangebot") or (subject contains "Jobs für"))
                repeat with m in msgs
                    if (count of msgList) >= {max_messages} then exit repeat
                    set end of msgList to {{id of m as string, source of m}}
                end repeat
            end try
            if (count of msgList) >= {max_messages} then exit repeat
        end repeat
    end tell

    set exportedCount to 0
    repeat with itemInfo in msgList
        try
            set msgId to item 1 of itemInfo
            set mSrc to item 2 of itemInfo
            set fPath to inboxPath & "alert_" & msgId & ".eml"
            set f to open for access (POSIX file fPath) with write permission
            set eof f to 0
            write mSrc to f as «class utf8»
            close access f
            set exportedCount to exportedCount + 1
        on error
            try
                close access (POSIX file fPath)
            end try
        end try
    end repeat

    return exportedCount
    """

    try:
        res = subprocess.run(["osascript", "-e", applescript], capture_output=True, text=True, check=True)
        count_str = res.stdout.strip()
        return int(count_str) if count_str.isdigit() else 0
    except Exception as e:
        print(f"Error communicating with Apple Mail: {e}")
        return 0
