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
      cwd: "/var/www/trading-robot",
      script: "dashboard.py",
      // Nao ha virtualenv nesta VPS: as dependencias estao no Python do sistema.
      interpreter: "python3",

      // --host 0.0.0.0 preserva o comportamento atual (o painel responde no IP
      // publico). Sem isso, o dashboard.py liga em 127.0.0.1 e so e alcancavel
      // de dentro da VPS. Veja a nota de exposicao no fim deste arquivo.
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

      out_file: "/var/www/trading-robot/logs/pm2-out.log",
      error_file: "/var/www/trading-robot/logs/pm2-error.log",
      merge_logs: true,
      time: true,
    },
  ],
};

// -------------------------------------------------------------------------- //
// Exposicao de rede
// -------------------------------------------------------------------------- //
// Com --host 0.0.0.0 o painel atende qualquer origem que alcance a porta 8000.
// Ele NAO tem autenticacao e guarda as chaves da Binance em texto puro em
// data/settings.json. Duas formas de fechar isso sem perder o acesso remoto:
//
//   1. Liberar a porta so para o seu IP (firewalld):
//        sudo firewall-cmd --permanent --zone=drop --add-source=SEU.IP.AQUI/32
//        sudo firewall-cmd --permanent --remove-port=8000/tcp
//        sudo firewall-cmd --reload
//
//   2. Trocar args para "--host 127.0.0.1 --port 8000 --no-browser" e acessar
//      por tunel SSH, do seu computador:
//        ssh -L 8000:127.0.0.1:8000 root@IP_DA_VPS
//      Depois abrir http://127.0.0.1:8000 no navegador local.
