# AiShopping API - Documentação

## Visão Geral

A AiShopping API é um sistema de pesquisa inteligente de produtos que utiliza IA para buscar, analisar e recomendar produtos com base nas especificações do usuário. A API oferece comunicação em tempo real através de Server-Sent Events (SSE) e funciona com um sistema de chat baseado em sessões.

## Base URL

```
http://localhost:3000
```

## Endpoints

### 1. Criar Nova Sessão de Chat

**POST** `/chats`

Cria uma nova sessão de chat e retorna um ID único para a sessão.

#### Response

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 2. Listar Chats

**GET** `/chats`

Retorna todas as sessões de chat ativas.

#### Response

```json
{
  "550e8400-e29b-41d4-a716-446655440000": "teclado mecânico",
  "550e8400-e29b-41d4-a716-446655440001": "smartphone android"
}
```

### 3. Interagir com Chat (Principal)

**POST** `/chats/{chat_id}`

Envia uma consulta para o agente de compras e recebe a resposta via Server-Sent Events.

#### Headers

```
Content-Type: application/json
Accept: text/event-stream
```

#### Body

```json
{
  "query": "Quero comprar um teclado mecânico",
  "specifications": "sem fio, até 1000 reais"
}
```

#### Parâmetros

- `query` (string, obrigatório): Descrição do produto que o usuário deseja comprar
- `specifications` (string, opcional): Especificações detalhadas do produto (preço, características, etc.)

#### Response

A resposta é transmitida via Server-Sent Events (SSE) com diferentes tipos de mensagens:

##### Tipos de Mensagens SSE

1. **Mensagens de Status/Progresso**
```
data: {"time": "2025-08-28_20-35-11", "id": "b11d3361-3468-4977-b9f8-5628065018a5", "type": "INFO", "content": "RECEPTIONIST 🤖 -> Entendi que você está procurando por..."}
```

2. **Informações de Pesquisa**
```
data: {"time": "2025-08-28_20-35-13", "id": "b11d3361-3468-4977-b9f8-5628065018a5", "type": "INFO", "content": "Searching: melhores teclados mecânicos sem fio até 1000 reais 2024"}
```

3. **Dados de Sites Sendo Analisados**
```
data: {"time": "2025-08-28_20-35-17", "id": "b11d3361-3468-4977-b9f8-5628065018a5", "type": "INFO", "content": {"site": "https://www.reddit.com/r/LogitechG/comments/19fe9t3/g915_tkl_worth_it_in_2024/?tl=pt-br", "icon": "https://www.google.com/s2/favicons?domain=www.reddit.com", "title": "", "id": "dffefa73-1c56-4e22-869f-4ab3a794e7b8", "start_time": 1756424117.6035047, "end_time": null}}
```

4. **Pergunta de Follow-up** (quando especificações não são fornecidas)
```
data: [ASK_HUMAN] Preciso de mais informações. Qual é o seu orçamento máximo? Você tem preferência por alguma marca específica?
```

5. **Resposta Final** (análise completa dos produtos)
```
data: [RESPONSE] # Análise Comparativa: Teclados Mecânicos Sem Fio até R$ 1000
[Markdown com análise detalhada dos produtos...]
```

6. **Mensagens de Controle**
```
data: [DONE]
data: [CANCELLED]
data: Execution time: 45.67s
```

#### Códigos de Status

- `200`: Sucesso - Stream de dados iniciado
- `404`: Chat não encontrado

## Fluxo de Uso

### Cenário 1: Consulta com Especificações Completas

1. **Criar chat**: `POST /chats`
2. **Enviar consulta completa**: `POST /chats/{chat_id}` com `query` e `specifications`
3. **Receber resposta**: Stream SSE com análise completa dos produtos

### Cenário 2: Consulta que Requer Follow-up

1. **Criar chat**: `POST /chats`
2. **Enviar consulta inicial**: `POST /chats/{chat_id}` apenas com `query`
3. **Receber pergunta**: Stream SSE com `[ASK_HUMAN]` solicitando mais informações
4. **Enviar especificações**: `POST /chats/{chat_id}` com o mesmo `chat_id`, `query` original e `specifications` baseadas na pergunta
5. **Receber resposta final**: Stream SSE com análise completa dos produtos

## Estrutura da Resposta Final

A resposta final é retornada como um documento Markdown estruturado contendo:

- **Contexto do Mercado**: Análise geral da categoria de produto
- **Análise Individual**: Revisão detalhada de cada produto encontrado
- **Comparativo**: Tabela comparativa dos melhores produtos
- **Recomendação**: Sugestão principal e alternativas

### Exemplo de Produto na Resposta

```json
{
  "name": "Logitech G515 TKL",
  "image": "https://m.media-amazon.com/images/I/71lVQORUsNL._AC_SL1500_.jpg",
  "model": "G515 TKL",
  "specifications": {
    "Tipo": "Mecânico Tenkeyless",
    "Conexão": "USB LightSpeed 2,4 GHz + Bluetooth + USB-C",
    "Switches": "GX Brown (Tátil silencioso)",
    "Layout": "ABNT2 brasileiro"
  },
  "pricing": {
    "price_range": "R$ 799 - R$ 900",
    "currency": "BRL",
    "last_updated": "2024-06-17"
  },
  "ratings": {
    "average_score": "4.0/5.0",
    "total_reviews": "indefinido",
    "pros": ["Alta versatilidade de conexão", "Layout ABNT2 nacional"],
    "cons": ["Sem software dedicado para iluminação"]
  },
  "availability": {
    "in_stock": true,
    "delivery_time": "2-5 dias úteis",
    "retailer": "Amazon Brasil"
  },
  "purchase_url": "https://amzn.to/3SzKGLo",
  "metadata": {
    "source_website": "https://www.guiadosperifericos.com.br/melhores-teclados-mecanicos/"
  }
}
```

## Considerações Técnicas

- **Timeout**: Conexões SSE podem ter timeout, implemente reconexão automática
- **Rate Limiting**: Evite múltiplas requisições simultâneas para o mesmo chat
- **Cancelamento**: O cliente pode fechar a conexão SSE para cancelar a operação
- **Encoding**: Todas as respostas utilizam UTF-8
- **CORS**: API configurada para aceitar requisições de qualquer origem

## Tratamento de Erros

- Conexões perdidas resultam em `[CANCELLED]`
- Erros internos são reportados como `Error: {mensagem}`
- Chats inexistentes retornam `404 Not Found`

Esta documentação deve facilitar a integração da API com interfaces frontend, permitindo criar experiências de usuário ricas e interativas para pesquisa de produtos com IA.
