## Cosa cambia

<!-- Breve descrizione delle modifiche -->

## Layer interessato

- [ ] L1 Voice & Audio
- [ ] L2 Brain & Reasoning
- [ ] L3 Memory & Knowledge
- [ ] L4 Tool Ecosystem
- [ ] L5 Team Agentico
- [ ] L6 Security
- [ ] L7 UI/UX & PWA
- [ ] L8 Infrastruttura
- [ ] Documentation / OSS

## Tipo

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] Documentation only
- [ ] Refactor / cleanup

## Test

- [ ] `python tests/full_system_test.py` passa (allega output se modifiche al brain/agents/memory)
- [ ] `python tests/security_redteam.py` passa (se modifiche a security/auth/prompt_shield)
- [ ] Testato a mano in browser
- [ ] Nessun nuovo file sensibile committato (vedi .gitignore)

## Compliance check

- [ ] Le modifiche NON degradano il livello GDPR/NIS2
- [ ] Se introduco nuovo trattamento dati: registrato in `data/gdpr_register.json`
- [ ] Se introduco nuovo tool sensibile: aggiunto in `tool_acl.HIGH_RISK` o `MEDIUM_RISK`

## Note per il revisore

<!-- Tutto quello che vorresti far notare -->
