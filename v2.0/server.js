const cors = require('cors');
const express = require('express');
const snmp = require('net-snmp');

const app = express();
const port = 3000;

// IP e comunidade SNMP de destino
const snmpTarget = '192.168.1.2'; // Seu IP local
const community = 'public';
const trapPort = 162; // Porta padrão SNMP

app.use(cors());
app.use(express.json());

app.post('/trap', (req, res) => {
    const value = req.body.value;
    console.log("📩 Requisição recebida para envio de trap, valor:", value);

    const session = snmp.createSession(snmpTarget, community, { port: trapPort });

    const varbinds = [
        {
            oid: "1.3.6.1.4.1.53864.1.1",
            type: snmp.ObjectType.Integer,
            value: value
        }
    ];

    session.trap(snmp.TrapType.EnterpriseSpecific, varbinds, (error) => {
        session.close();
        if (error) {
            console.error("❌ Erro ao enviar trap:", error);
            res.status(500).send("Erro ao enviar trap");
        } else {
            console.log("✅ Trap SNMP enviada com valor:", value);
            res.send("Trap enviada");
        }
    });
});

app.listen(port, () => {
    console.log(`🚀 Servidor Express rodando em http://localhost:${port}`);
});
