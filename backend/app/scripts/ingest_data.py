"""Shim module for legacy start command compatibility."""
import sys
# Startup sync is already handled by app lifespan / railway_start
sys.exit(0)
