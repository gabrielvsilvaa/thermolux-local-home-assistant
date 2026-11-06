# Thermolux Local

Integração comunitária para controlar toalheiros Thermolux Easy-IV pela rede local, via TCP 8090. Inclui seleção de modo, desligamento, leitura de estado, agendas diárias e um card com enquadramento e envio de foto de descanso.

## Compatibilidade

Testada em duas unidades Easy-IV com Home Assistant OS 2026.8.0. Outros modelos ainda não foram verificados. O toalheiro precisa estar conectado à rede local e acessível pelo Home Assistant. Use uma conta administradora para configurar a integração e usar os controles do card.

## Instalação manual

1. Copie `custom_components/thermolux_local` para a pasta `custom_components` da configuração do Home Assistant.
2. Reinicie o Home Assistant.
3. Em **Configurações → Dispositivos e serviços → Adicionar integração**, procure **Thermolux Local**. Informe o nome e o IPv4 do toalheiro.
4. Abra a engrenagem da entrada do aparelho, selecione o dashboard e a aba e confirme. Em dashboards gerenciados pela interface, o recurso do card é registrado pela integração. Se os recursos forem gerenciados por YAML, adicione `/thermolux_local/card.js?v=0.3.0` como módulo JavaScript.
5. Abra a agenda no card, crie os horários e ative a agenda quando estiver pronta.

## Limitações

- O retorno automático após falta de energia ainda está em investigação. Algumas unidades podem precisar de um toque no painel para voltar à rede.
- Se o aparelho estiver inacessível na hora programada, o comando daquele horário não é repetido automaticamente.
- O botão nativo da página do dispositivo usa as sugestões do Home Assistant. Use a engrenagem da integração para adicionar o card completo.
- A agenda e a foto são armazenadas localmente e associadas à identidade do aparelho.

## Instalação pelo HACS

Em **HACS → Repositórios personalizados**, adicione `https://github.com/gabrielvsilvaa/thermolux-local` como **Integração**, baixe **Thermolux Local** e reinicie o Home Assistant. Depois, siga os passos de cadastro acima.

Versão inicial de teste, sem vínculo com o fabricante.
