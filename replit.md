# GLM APP DEL CULTIVADOR ARGENTINO

## Overview
GLM APP DEL CULTIVADOR ARGENTINO is a Streamlit-based plant cultivation management application designed for growers in La Carlota, Córdoba, Argentina. It offers a comprehensive suite of tools including weather monitoring, personalized cultivation advice, advanced irrigation calculations, plant diagnostics with natural remedies, harvest estimation, legal guidance (REPROCANN), and detailed cultivation tracking. The application aims to provide a Jamaican-themed, user-friendly interface to assist cultivators in optimizing their plant growth and adhering to local regulations, with a strong focus on natural methods and local climate conditions. The project envisions market potential for broader adoption within the Argentine cultivation community, supporting sustainable and informed growing practices.

## User Preferences
- All advice tailored to La Carlota climate (alkaline pH ~7.5, hard water, seasonal pests)
- Emphasize natural and homemade remedies (caseros)
- System-specific recommendations throughout
- Spanish language (Argentine)

## System Architecture
The application is built using Python 3.12 and the Streamlit framework, providing a dynamic web interface. It integrates with a PostgreSQL database (Neon-backed) for data persistence.

**UI/UX Decisions:**
- **Theme:** Jamaican-style (green, yellow, red, black) with cannabis-themed imagery (logo, banners, decorative dividers).
- **Visuals:** Features glass-morphism metric cards, smooth CSS transitions, custom scrollbars, enhanced hover states for interactive elements, and AI-generated icons for modules and UI elements.
- **Dynamic Interface:** Incorporates CSS keyframe animations like centered logo with floating animation, shimmer effects, fadeInUp entrance animations, pulseGlow on metric cards, and borderGlow on the sidebar for a modern and engaging user experience.
- **Mobile Experience:** Includes an Android Studio project for a WebView wrapper, ensuring mobile responsiveness and Play Store publication.
- **Language:** Entirely in Argentine Spanish.

**Technical Implementations & Feature Specifications:**
- **Modules:**
    1.  **Clima y Sugerencias:** Weather monitoring via Open-Meteo API, VPD calculations, 3-day forecast, Windy radar, and geolocation-based daily recommendations.
    2.  **Asesoramiento Cultivo:** Substrate, watering, and environment tips with links to local grow shops.
    3.  **Calculadora Riego:** Personalized irrigation calculations based on cultivation specifics (volume, frequency, pH, water type, nutrition, technique) and real-time weather.
    4.  **Diagnóstico & Plagas:** Plant diagnostics covering 5 zones and 11 symptoms, offering natural remedies and system-specific advice.
    5.  **Estimador de Cosecha:** Harvest estimation with a comprehensive 6-tab guide (signals, trichomes, yield, flush/cutting, drying, curing) adapted per cultivation.
    6.  **Sugerencias Legales:** REPROCANN legal guidance including registration, requirements, limits, rights/FAQ, and an auto-updating news feed from Google News RSS.
    7.  **Seguimiento de Cultivo:** Multi-cultivation tracking with stage detection, step-by-step guidance for 8-9 stages per system, and pot-size adjustments.
- **Geolocation:** Browser-based detection with `streamlit-js-eval`, Nominatim OpenStreetMap for reverse geocoding, defaulting to La Carlota if unavailable or unchecked.
- **Cultivation Systems:** Supports 7 types across 3 categories: Interior (Luz, Automáticas), Exterior (Maceta, Tierra Madre, Automáticas), and Invernadero (Maceta, Tierra).
- **Monetization:** Subscription model (weekly, monthly, annual plans, 7-day free trial) implemented via Mercado Pago Checkout Pro, gating premium modules.
- **Referral System:** Subscribers can earn a free annual subscription by referring 5 users who subscribe to the annual plan.
- **Data Persistence:** All application data, including subscriptions and cultivation details, is stored in a PostgreSQL database.

## External Dependencies
- **APIs:**
    -   Open-Meteo API (for weather data)
    -   Nominatim OpenStreetMap API (for reverse geocoding)
    -   Google News RSS (for legal news feed)
    -   Mercado Pago API (for payment verification and subscription management)
- **Payment Gateway:**
    -   Mercado Pago Checkout Pro (for ARS currency transactions)
- **Database:**
    -   PostgreSQL (Neon-backed)
- **Libraries:**
    -   pandas
    -   numpy
    -   requests
    -   streamlit-js-eval
    -   mercadopago
    -   psycopg2-binary