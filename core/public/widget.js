const goalTitle = document.getElementById("goalTitle");
const goalPercent = document.getElementById("goalPercent");
const goalFill = document.getElementById("goalFill");
const currentAmount = document.getElementById("currentAmount");
const goalAmount = document.getElementById("goalAmount");
const lastDonation = document.getElementById("lastDonation");

function niceNumber(value) {
  const number = Number(value) || 0;
  return Math.floor(number).toLocaleString("ru-RU");
}

function render(state) {
  const current = Number(state.current) || 0;
  const goal = Number(state.goal) || 1;
  const currency = state.currency || "RUB";

  const percent = Math.min((current / goal) * 100, 100);
  const percentText = Math.floor(percent);

  goalTitle.textContent = state.title || "Сбор на цель";
  goalPercent.textContent = "";

  goalFill.style.width = `${percent}%`;

  currentAmount.textContent = `${niceNumber(current)} / ${niceNumber(goal)} ${currency} (${percentText}%)`;
  goalAmount.textContent = "";

  lastDonation.textContent = "";
}

async function update() {
  try {
    const response = await fetch("/api/state?t=" + Date.now());
    const state = await response.json();
    render(state);
  } catch (error) {
    console.error("Не удалось получить состояние цели", error);
  }
}

update();
setInterval(update, 700);