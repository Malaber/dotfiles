https://youtrack.jetbrains.com/issue/IJPL-177161/Modal-commit-moved-to-a-separate-plugin-in-2025.1-Discussion#focus=Change-27-11573772.0-0.pinned

> That said, it does seem like EAP 2025.1 has enough options to allow the "non-modal" Git window to behave exactly like the "Local Changes" window did previously. With a combination of settings you can rebuild the the "Local Changes" tab:

> Disable "Advanced Settings -> Enable commit tool window". This merges the "commit" and "git" panels and restores the "preview diff" toggle button for the panel.
> Disable "Git -> Enable Staging Area." This will display your uncommited changes as a single list instead of staged vs unstaged.
> Enable "Advanced Settings -> Toggle Commit Controls." This will add a "commit" button to the panel which toggles the per-file git commit checkboxes and commit message box in-place. (Actually kind-of cool)
> Open the "Git" panel
> Presumably you might set the view mode to "windowed"
> Enable "Preview Diff"
> So I don't want to dismiss any of the concerns above, but if you're only here for the "Local Changes" window I think its all here now. Maybe also try the guide posted above and see if it works for you.
