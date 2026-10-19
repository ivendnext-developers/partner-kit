/* ivn-kit 0.1.0 · SAMPLE tenant themes, for the till-sheet template only.
 * In a real page this object arrives in the signed context's `theme` field; it is kept
 * out of the template so the template itself stays "tokens only".
 * Values: a POS-like look taken from design_system/foundations/00-tokens-pos.html and
 * 00-tokens-pos-dark.html (iVendNext_PWA @ 05bb4dab92f294edac7b9d5bbac697d3072a4978).
 * A defect here is a defect there — report it on Retail mPOS's board. */
window.IVN_SAMPLE_THEMES = {
  light: { mode: "light", vars: {
    "--ivn-primary": "rgb(14,96,130)", "--ivn-primary-strong": "rgb(11,77,105)",
    "--ivn-focus": "#1a73e8", "--ivn-bg": "#fbfbfc",
    "--ivn-radius": "4px", "--ivn-radius-lg": "4px", "--ivn-font-scale": "1.07" } },
  dark: { mode: "dark", vars: {
    "--ivn-primary": "#8fd0e6", "--ivn-primary-strong": "rgb(42,111,134)",
    "--ivn-focus": "#6ab0f3",
    "--ivn-radius": "4px", "--ivn-radius-lg": "4px", "--ivn-font-scale": "1.07" } }
};
