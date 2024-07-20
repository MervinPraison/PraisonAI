const theme = localStorage.getItem('theme') || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
document.documentElement.setAttribute("data-theme", theme);

document.addEventListener('DOMContentLoaded', (event) => {
  const toggleSwitch = document.querySelector('.theme-switch input[type="checkbox"]');
  if (theme === 'dark') {
    toggleSwitch.checked = true;
  }
  toggleSwitch.addEventListener('change', switchTheme, false);
});

function switchTheme(e) {
  if (e.target.checked) {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('theme', 'light');
  }
}