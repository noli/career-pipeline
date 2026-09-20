-- Apple Mail Rule Script for Career Pipeline
-- Place in ~/Library/Application Scripts/com.apple.mail/
using terms from application "Mail"
	on perform mail action with messages theMessages for rule theRule
		-- Configure your inbox path below:
		set homeDir to POSIX path of (path to home folder as text)
		set inboxDir to homeDir & "Documents/Career/Inbox/" -- Customize to your local Career/Inbox directory
		
		tell application "Mail"
			repeat with aMessage in theMessages
				try
					set msgId to id of aMessage as string
					set mSrc to source of aMessage
					set fPath to inboxDir & "alert_" & msgId & ".eml"
					
					set f to open for access (POSIX file fPath) with write permission
					set eof f to 0
					write mSrc to f as «class utf8»
					close access f
				on error
					try
						close access (POSIX file fPath)
					end try
				end try
			end repeat
		end tell
	end perform mail action with messages
end using terms from
