// Configuracao PM2 do painel do Robo de Trading DQN.
//
//   pm2 start deploy/ecosystem.config.js
//   pm2 save
//
// ATENCAO ao numero de instancias: o painel sobe uma thread de agendador dentro
// do processo (webapp/automation.py). Cada instancia do PM2 e um PROCESSO
// separado, com a sua propria copia do agendador -- duas instancias significam
// dois robos lendo o mesmo catalogo e disparando a MESMA ordem em duplicidade.
// Por isso: instances 1 e exec_mode "fork". Nunca use "cluster" aqui.

module.exports = {
  apps: [
    {
      name: "dqn-dashboard",
      cwd: "/opt/trading-robot",
      script: "dashboard.py",
      interpreter: "/opt/trading-robot/.venv/bin/python",
      args: "--host 0.0.0.0 --port 8000 --no-browser",

      instances: 1,
      exec_mode: "fork",

      // O robo guarda estado em disco (carteira, log). Reinicios automaticos por
      // uso de memoria ou por watch de arquivo cortariam um ciclo no meio.
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 10000,

      env: {
        // A B3 opera no horario de Brasilia e o agendador usa a hora local.
        TZ: "America/Sao_Paulo",
        PYTHONUNBUFFERED: "1",
        // Torch abrindo uma thread por nucleo em VPS pequena so gera disputa.
        OMP_NUM_THREADS: "2",
      },

      out_file: "/opt/trading-robot/logs/pm2-out.log",
      error_file: "/opt/trading-robot/logs/pm2-error.log",
      merge_logs: true,
      time: true,
    },
  ],
};
