Background Daemon
=================

The optional background daemon watches for file changes and keeps the index updated automatically, making CLI commands near-instant.

.. note::

   The daemon is completely optional. When not running, ``nb`` works exactly as before with on-demand indexing. The daemon simply provides faster performance by keeping the index up-to-date in the background.

Installation
------------

The daemon requires the ``watchdog`` package:

.. code-block:: bash

   uv sync --extra daemon
   # or
   uv pip install watchdog

Commands
--------

Start/Stop
^^^^^^^^^^

.. code-block:: bash

   nb daemon start           # Start background watcher (daemonized)
   nb daemon start -f        # Run in foreground (useful for debugging)
   nb daemon stop            # Stop the daemon
   nb daemon restart         # Restart the daemon

Status
^^^^^^

.. code-block:: bash

   nb daemon status          # Check if running, show stats

Example output:

.. code-block:: text

   ● Daemon is running
     PID              47592
     Uptime           2h 15m
     Files indexed    42
     Files removed    3
     Errors           0
     Last activity    5s ago

Logs
^^^^

.. code-block:: bash

   nb daemon log             # View last 50 lines of daemon log
   nb daemon log -n 100      # View last 100 lines
   nb daemon log -f          # Follow log output (like tail -f)

What Gets Watched
-----------------

The daemon monitors:

- All notebooks under ``notes_root``
- External notebook paths (configured with ``path:`` in notebooks)
- Linked todo files (added with ``nb link add``)
- Linked note files/directories

When a ``.md`` file changes, the daemon:

1. Waits 2 seconds for changes to settle (debouncing)
2. Re-indexes the file (updates notes table and todos)
3. Removes deleted files from the index

How It Works
------------

When the daemon is running:

- Commands like ``nb todo`` and ``nb search`` detect the daemon and skip their normal indexing step
- File changes are picked up within seconds
- The index stays current even when editing notes in external editors

Daemon files are stored in ``.nb/``:

- ``daemon.pid`` - Process ID file
- ``daemon.state`` - Status and statistics (JSON)
- ``daemon.log`` - Log output

Running as a System Service
---------------------------

For the best experience, configure the daemon to start automatically when you log in.

The daemon automatically loads configuration from ``~/notes/.nb/config.yaml`` when run without arguments.

Finding the Executable Path
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you installed nb with ``uv``, find the executable path:

.. code-block:: bash

   # If installed as a tool
   uv tool run --from nb-cli which nb-daemon

   # If installed in a project
   uv run which nb-daemon   # Unix/macOS
   uv run where nb-daemon   # Windows

Common locations:

- **uv tool install**: ``~/.local/bin/nb-daemon``
- **venv**: ``.venv/bin/nb-daemon`` or ``.venv/Scripts/nb-daemon.exe``

Windows (Task Scheduler)
^^^^^^^^^^^^^^^^^^^^^^^^

**Option 1: Manual Setup**

1. Open Task Scheduler (``taskschd.msc``)
2. Click "Create Task..."
3. **General tab**:

   - Name: ``nb-daemon``
   - Check "Run only when user is logged on"

4. **Triggers tab**:

   - New trigger: "At log on"

5. **Actions tab**:

   - New action: Start a program
   - Program: Full path to ``nb-daemon.exe`` (e.g., ``C:\Users\yourname\.local\bin\nb-daemon.exe``)

6. **Settings tab**:

   - Check "Run task as soon as possible after a scheduled start is missed"
   - Set "Stop the task if it runs longer than" to "Disabled" (or remove the limit)

**Option 2: Import XML**

Save this as ``nb-daemon.xml`` (update the path):

.. code-block:: xml

   <?xml version="1.0" encoding="UTF-16"?>
   <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
     <RegistrationInfo>
       <Description>nb background indexing daemon</Description>
     </RegistrationInfo>
     <Triggers>
       <LogonTrigger>
         <Enabled>true</Enabled>
       </LogonTrigger>
     </Triggers>
     <Principals>
       <Principal>
         <LogonType>InteractiveToken</LogonType>
       </Principal>
     </Principals>
     <Actions>
       <Exec>
         <Command>C:\Users\yourname\.local\bin\nb-daemon.exe</Command>
       </Exec>
     </Actions>
     <Settings>
       <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
       <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
       <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
       <AllowStartOnDemand>true</AllowStartOnDemand>
     </Settings>
   </Task>

Import the task:

.. code-block:: powershell

   schtasks /create /tn "nb-daemon" /xml nb-daemon.xml

To remove:

.. code-block:: powershell

   schtasks /delete /tn "nb-daemon" /f

macOS (launchd)
^^^^^^^^^^^^^^^

Create ``~/Library/LaunchAgents/com.nb.daemon.plist``:

.. code-block:: xml

   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.nb.daemon</string>
       <key>ProgramArguments</key>
       <array>
           <string>/Users/yourname/.local/bin/nb-daemon</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <true/>
       <key>StandardOutPath</key>
       <string>/tmp/nb-daemon.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/nb-daemon.err</string>
   </dict>
   </plist>

Update the path to match your setup, then load:

.. code-block:: bash

   launchctl load ~/Library/LaunchAgents/com.nb.daemon.plist

To check status:

.. code-block:: bash

   launchctl list | grep nb

To unload:

.. code-block:: bash

   launchctl unload ~/Library/LaunchAgents/com.nb.daemon.plist

Linux (systemd user service)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Create ``~/.config/systemd/user/nb-daemon.service``:

.. code-block:: ini

   [Unit]
   Description=nb indexing daemon
   After=default.target

   [Service]
   Type=simple
   ExecStart=/home/yourname/.local/bin/nb-daemon
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target

Update the path, then enable and start:

.. code-block:: bash

   # Reload systemd to pick up the new service
   systemctl --user daemon-reload

   # Enable auto-start on login
   systemctl --user enable nb-daemon

   # Start now
   systemctl --user start nb-daemon

To check status:

.. code-block:: bash

   systemctl --user status nb-daemon

To view logs:

.. code-block:: bash

   journalctl --user -u nb-daemon -f

To stop and disable:

.. code-block:: bash

   systemctl --user stop nb-daemon
   systemctl --user disable nb-daemon

Custom Config Location
^^^^^^^^^^^^^^^^^^^^^^

If your config is not at ``~/notes/.nb/config.yaml``, pass the path:

.. code-block:: bash

   nb-daemon /path/to/config.yaml

Update your service configuration accordingly.

Troubleshooting
---------------

Daemon won't start
^^^^^^^^^^^^^^^^^^

1. Check if watchdog is installed:

   .. code-block:: bash

      python -c "import watchdog; print('OK')"

2. Check the log file at ``.nb/daemon.log`` for errors

3. Try running in foreground to see errors directly:

   .. code-block:: bash

      nb daemon start -f

Daemon not detecting changes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Check status to confirm it's running:

   .. code-block:: bash

      nb daemon status

2. Check the log for "Watching:" entries to confirm paths are correct:

   .. code-block:: bash

      nb daemon log | grep "Watching"

3. Make sure the file is a ``.md`` file (other extensions are ignored)

4. Hidden files (starting with ``.``) are ignored

High CPU usage
^^^^^^^^^^^^^^

This is rare but can happen with very large note collections or fast file changes. The 2-second debounce should prevent most issues. If you experience high CPU:

1. Check ``nb daemon log`` for rapid indexing activity
2. Consider if you have external tools modifying many files at once
3. Stop the daemon and use on-demand indexing instead

Stale PID file
^^^^^^^^^^^^^^

If the daemon crashed and left a stale PID file, ``nb daemon status`` will automatically clean it up. You can also manually delete ``.nb/daemon.pid`` and ``.nb/daemon.state``.
