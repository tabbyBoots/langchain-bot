"""
DEBUG FILE: Fixes for rename dialog not closing and refresh issues
================================================================

This file contains code snippets to fix two issues:
1. Rename dialog not closing after save
2. Frontend showing old name after page refresh (while DB has new name)

INSTRUCTIONS: Manually copy these fixes to main.py following the steps below.
"""

# ==============================================================================
# FIX 1: Update save_message_with_subject function
# ==============================================================================
# LOCATION: Replace lines 203-231 in main.py
# REASON: The current function tries to fetchone() from an UPDATE statement,
#         which causes "the last operation didn't produce records" error

def save_message_with_subject(session_id: str, subject: str = None):
    """
    Update the subject for the most recent message in a session.
    Called after the first user message to set the default subject.
    """
    if db_conn is None:
        return
    try:
        with db_conn.cursor() as cur:
            if subject:
                # First message: Set the provided subject for all NULL subjects
                cur.execute("""
                    UPDATE chat_history
                    SET subject = %s
                    WHERE session_id = %s AND subject IS NULL;
                """, (subject, session_id))
                print(f" Set subject for session {session_id}: {subject}")
            else:
                # Subsequent messages: Get existing subject and apply to NULL entries
                cur.execute("""
                    SELECT subject
                    FROM chat_history
                    WHERE session_id = %s AND subject IS NOT NULL
                    LIMIT 1;
                """, (session_id,))
                result = cur.fetchone()

                if result and result[0]:
                    existing_subject = result[0]
                    cur.execute("""
                        UPDATE chat_history
                        SET subject = %s
                        WHERE session_id = %s AND subject IS NULL;
                    """, (existing_subject, session_id))
                    print(f" Applied existing subject '{existing_subject}' to new messages in session {session_id}")
    except Exception as e:
        print(f"� Error setting subject: {e}")


# ==============================================================================
# FIX 2: Update CSS for rename dialog
# ==============================================================================
# LOCATION: Find #rename-dialog CSS section (around line 1406-1418) in main.py
# REASON: The !important flags prevent JavaScript from hiding the dialog
#
# CURRENT CODE (BROKEN):
#     #rename-dialog {
#         display: block !important;       /* � This prevents hiding! */
#         visibility: visible !important;  /* � This prevents hiding! */
#         opacity: 1 !important;          /* � This prevents hiding! */
#     }
#
# REPLACE WITH:

CSS_FIX_RENAME_DIALOG = """
        /* Rename dialog - highly visible */
        #rename-dialog {
            background: #fff3cd !important;
            border: 2px solid #ffc107 !important;
            border-radius: 8px !important;
            padding: 1.5rem !important;
            margin: 1rem 0 !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
            position: relative !important;
            z-index: 100 !important;
        }

        /* Show dialog when visible */
        #rename-dialog:not([style*="display: none"]) {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        /* Hide dialog when hidden */
        #rename-dialog[style*="display: none"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
        }
"""


# ==============================================================================
# FIX 3: Update save_rename_btn.click JavaScript
# ==============================================================================
# LOCATION: Find save_rename_btn.click (around lines 768-788) in main.py
# REASON: Need to force the dialog to close properly
#
# REPLACE THE .then() PART WITH:

JAVASCRIPT_FIX_CLOSE_DIALOG = """
).then(
    fn=None,
    inputs=None,
    outputs=None,
    js="""() => {
        console.log('[Save] Post-save: Hiding dialog and forcing refresh');
        const dialog = document.getElementById('rename-dialog');
        if (dialog) {
            // Force hide with inline style
            dialog.style.cssText = 'display: none !important;';
            console.log('[Save] Dialog hidden via JavaScript');
        }

        // Double-check after a small delay
        setTimeout(() => {
            if (dialog) {
                dialog.style.display = 'none';
                console.log('[Save] Verified dialog is hidden');
            }
        }, 100);
    }"""
)
"""


# ==============================================================================
# FIX 4: Update save_rename function return statement
# ==============================================================================
# LOCATION: Line 766 in main.py
# REASON: Explicitly update the input field to ensure it clears
#
# CURRENT CODE:
#     return html, gr.update(visible=False), "", ""
#
# REPLACE WITH:
#     return (
#         html,                           # Updated session list
#         gr.update(visible=False),       # Hide dialog
#         "",                             # Clear session ID state
#         gr.update(value="")            # Clear input with explicit update
#     )


# ==============================================================================
# STEP-BY-STEP APPLICATION GUIDE
# ==============================================================================
"""
STEP 1: Fix the save_message_with_subject function
--------------------------------------------------
1. Open main.py
2. Find the function save_message_with_subject (lines 203-231)
3. Select the entire function
4. Replace it with the version from FIX 1 above
5. Save the file

This fixes the "the last operation didn't produce records" error.


STEP 2: Fix the CSS for rename dialog
--------------------------------------
1. In main.py, find the CSS section inside demo.launch()
2. Locate the #rename-dialog { } block (around line 1406)
3. Find these three lines:
       display: block !important;
       visibility: visible !important;
       opacity: 1 !important;
4. DELETE those three lines
5. Add the new CSS rules from CSS_FIX_RENAME_DIALOG above
6. Save the file

This allows the dialog to be hidden via JavaScript.


STEP 3: Update the JavaScript for closing dialog
-------------------------------------------------
1. In main.py, find save_rename_btn.click (around line 768)
2. Find the .then() block that comes right after it
3. Replace the entire .then() block with the one from JAVASCRIPT_FIX_CLOSE_DIALOG
4. Make sure the parentheses match up correctly
5. Save the file

This forces the dialog to close after saving.


STEP 4: Update the return statement in save_rename
---------------------------------------------------
1. In main.py, find the save_rename function (around line 737)
2. Find the last return statement (around line 766):
       return html, gr.update(visible=False), "", ""
3. Replace it with:
       return (
           html,                           # Updated session list
           gr.update(visible=False),       # Hide dialog
           "",                             # Clear session ID state
           gr.update(value="")            # Clear input with explicit update
       )
4. Save the file

This ensures the input field is properly cleared.


STEP 5: Test the fixes
-----------------------
1. Stop the application (Ctrl+C)
2. Restart: uv run main.py
3. Test renaming a session
4. The dialog should close after clicking Save
5. Refresh the page (F5)
6. The session list should show the new name


TROUBLESHOOTING
---------------
If the dialog still doesn't close:
- Check browser console (F12) for JavaScript errors
- Make sure all CSS !important flags are removed from display/visibility/opacity
- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)

If the name doesn't update after refresh:
- Check database: docker exec -it langchain_postgres psql -U langchain -d langchain_chat
- Run: SELECT session_id, subject FROM chat_history WHERE session_id = 'your-session-id';
- If DB is correct but UI is wrong, it's likely a browser cache issue
"""
