/** @type {import('tailwindcss').Config} */
export default {
    content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
    theme: {
        extend: {
            colors: {
                dark: {
                    bg: "#0d1426",
                    surface: "#16213a",
                    elevated: "#1d2b47",
                    card: "#1f3150",
                },
            },
            fontFamily: {
                sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
                display: ["Space Grotesk", "Inter", "sans-serif"],
            },
            boxShadow: {
                "glow-violet": "0 0 30px rgba(124,58,237,0.4)",
                "glow-cyan": "0 0 30px rgba(34,211,238,0.3)",
            },
            keyframes: {
                "spin-slow": { to: { transform: "rotate(360deg)" } },
            },
            animation: {
                "spin-slow": "spin-slow 3s linear infinite",
            },
        },
    },
    plugins: [],
};
