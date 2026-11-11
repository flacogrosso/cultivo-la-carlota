mkdir -p ~/.streamlit/
echo "[server]
headless = true
port = 5000
address = \"0.0.0.0\"
enableCORS = true
enableXsrfProtection = true
" > ~/.streamlit/config.toml