#!/bin/bash

# Sync crawl_output.json to Google Drive
rclone copy crawl_output.json gdrive:/spider-crawl/ --update