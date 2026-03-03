#!/bin/bash
# System audit: multiple command executions, report generation
# Tests: command execution (date, disk, python, processes), file creation, file reading

praisonai "Investigate my system - get the current date, check disk usage, find out what Python version is installed, list running processes sorted by memory, then write all findings to /tmp/system_audit.md as a neat report and read it back to verify" --trust
