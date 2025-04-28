const cors = require('cors');


const express = require('express');
const snmp = require('net-snmp');
const fs = require('fs');

const app = express();
const port = 3000;



// IP e comunidade SNMP de destino
const snmpTarget = '192.168.1.2'; // Seu IP local
const community = 'public';
const trapPort = 162; // ou use 3000 para testes

// Valor atual do status do vídeo
let videoStatus = 1; // 1 = OK, 2 = Congelado
app.use(cors());
app.use(express.json());

// Endpoint que recebe status do HTML
app.post('/trap', (req, res) => {
    const value = req.body.value;

    // Atualiza status
    videoStatus = value;

    // Envia trap SNMP
    const session = snmp.createSession(snmpTarget, community, { port: trapPort });

    const varbinds = [
        {
            oid: "1.3.6.1.4.1.53864.1.1",
            type: snmp.ObjectType.Integer,
            value: videoStatus
        }
    ];

    session.trap(snmp.TrapType.EnterpriseSpecific, varbinds, (error) => {
        session.close();
        if (error) {
            console.error("Erro ao enviar trap:", error);
            res.status(500).send("Erro ao enviar trap");
        } else {
            console.log(`📤 Trap enviada com valor ${videoStatus}`);
            res.send("Trap enviada");
        }
    });
});

// Endpoint para consultar o status atual
app.get('/status', (req, res) => {
    res.json({ status: videoStatus });
});

app.listen(port, () => {
    console.log(`🚀 Servidor Express rodando em http://localhost:${port}`);
});

app.post('/trap', (req, res) => {
    const value = req.body.value;
    console.log("📩 Requisição recebida com valor:", value); // <- LOG DE ENTRADA

    videoStatus = value;

    const session = snmp.createSession(snmpTarget, community, { port: trapPort });

    const varbinds = [
        {
            oid: "1.3.6.1.4.1.53864.1.1",
            type: snmp.ObjectType.Integer,
            value: videoStatus
        }
    ];

    console.log("📤 Enviando trap SNMP para", snmpTarget, "na porta", trapPort); // <- LOG ANTES

    session.trap(snmp.TrapType.EnterpriseSpecific, varbinds, (error) => {
        session.close();
        if (error) {
            console.error("❌ Erro ao enviar trap:", error);
            res.status(500).send("Erro ao enviar trap");
        } else {
            console.log("✅ Trap enviada com sucesso com valor", videoStatus);
            res.send("Trap enviada");
        }
    });
});
