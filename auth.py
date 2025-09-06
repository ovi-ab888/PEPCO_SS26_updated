# auth.py
import os
import streamlit as st

def check_password():
    """
    Secrets -> env fallback. ভুল পাসওয়ার্ডে error দেখায়।
    .streamlit/secrets.toml এ app_password, নাহলে env PEPCO_APP_PASSWORD লাগে।
    """
    expected = None
    try:
        expected = st.secrets.get("app_password", None)
    except Exception:
        expected = None
    if expected is None:
        expected = os.environ.get("PEPCO_APP_PASSWORD")

    if expected is None:
        st.error("App password not configured. Set 'app_password' in .streamlit/secrets.toml or PEPCO_APP_PASSWORD env var.")
        return False

    def _submit():
        st.session_state["password_ok"] = (st.session_state.get("password") == expected)
        # নিরাপত্তার জন্য ইন-মেমোরি টেক্সট মুছে ফেলি
        if "password" in st.session_state:
            try: del st.session_state["password"]
            except Exception: pass

    if st.session_state.get("password_ok") is True:
        return True

    st.text_input("Password", type="password", key="password", on_change=_submit)
    if st.session_state.get("password_ok") is False:
        st.error("Your password Incorrect,  Please contact Mr. Ovi")
    return False
