const snmp = require('net-snmp-agent');

// Status atual do vídeo
let videoStatus = 1; // 1 = OK, 2 = Congelado

// Configuração do agente
const agent = snmp.createAgent({
  name: "meu-agente-snmp",
  port: 161, // Use 8161 se não puder abrir a 161 direto
  accessControlModelType: snmp.AccessControlModelType.Simple,
  community: "public"
});

// Criação do OID monitorado
agent.setScalarValue("1.3.6.1.4.1.53864.1.1", snmp.ObjectType.Integer, () => videoStatus);

agent.on("listening", () => {
  console.log("✅ Agente SNMP ouvindo em porta 161 (GET habilitado)");
});

agent.on("request", (req) => {
  console.log(`📥 GET recebido de ${req.rinfo.address}`);
});
