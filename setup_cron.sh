#!/bin/bash

# Add cron job to sync every 2 minutes
(crontab -l 2>/dev/null; echo "*/2 * * * * cd $(pwd) && ./sync_to_gdrive.sh") | crontab -