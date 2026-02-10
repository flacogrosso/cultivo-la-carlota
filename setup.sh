mkdir -p ~/.streamlit/
echo "[server]
headless = true
port = 5000
address = \"0.0.0.0\"
enableCORS = false
enableXsrfProtection = false
" > ~/.streamlit/config.toml