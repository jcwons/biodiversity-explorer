"""
gee_utils.py

Helper functions to safely initialize Google Earth Engine (EE)
using a service account. Designed for Streamlit apps where
secrets are stored in st.secrets.
"""

import ee

# -----------------------------
# Global flag to prevent re-initialization
_initialized = False

def init_ee(credentials):
    """
    Initialize Google Earth Engine using provided credentials.
    
    This function is idempotent: calling it multiple times will
    not re-initialize EE.
    
    Args:
        credentials (ee.ServiceAccountCredentials): EE service account credentials.
    """
    global _initialized
    if not _initialized:
        ee.Initialize(credentials)
        _initialized = True

def is_ee_initialized():
    """
    Check whether EE has already been initialized.
    
    Returns:
        bool: True if EE is initialized, False otherwise.
    """
    return _initialized
