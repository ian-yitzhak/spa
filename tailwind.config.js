// Build: ./bin/build-css  (see README). Output static/css/tw.css is committed and served by nginx.
module.exports = {
  content: ["./templates/**/*.html", "./*/**/*.py", "!./**/migrations/**", "!./.venv/**"],
  theme: { extend: {
    colors: { primary: "#B0426C", dark: "#221A1F", accent: "#E8B4C4", gold: "#C9A227" },
    borderRadius: { md: "3px", lg: "4px", xl: "5px", "2xl": "6px", "3xl": "8px" },
    fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], heading: ["Poppins", "Inter", "sans-serif"] },
  } },
};
