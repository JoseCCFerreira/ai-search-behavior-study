# Manual: Dashboard Offline e Upload de Atividades

Este manual explica como usar o dashboard Streamlit em modo offline/local, atualizar a base DuckDB dedicada e analisar desempenho por ano, mês, período, tipo de atividade, rota GPS e zonas geográficas.

## 1. Abrir a app

Na pasta do projeto:

```bash
streamlit run app/streamlit_app.py --server.port 8501
```

Depois abre:

```text
http://localhost:8501
```

## 2. Base de dados dedicada

A app usa a base DuckDB configurada em:

```text
database/strava_coach.duckdb
```

Este caminho vem da variável `DUCKDB_PATH`. Para usar outra base dedicada, muda no ficheiro `.env`:

```text
DUCKDB_PATH=database/minha_base_strava.duckdb
```

A app cria e migra o schema automaticamente quando arranca.

## 3. Sem ligação direta ao Strava

O dashboard atual funciona em modo offline. Não existe botão para ligar/autorizar o Strava na interface.

Os dados entram através de upload de ficheiros exportados/descarregados:

- export completo `.zip` do Strava
- atividade individual `.gpx`
- atividade individual `.fit`
- atividade individual `.tcx`
- ficheiros comprimidos `.gz`
- extensão `.git`, tratada como ficheiro FIT se o conteúdo for válido

## 4. Upload de atividades

Na sidebar, usa a secção `Upload Activities`.

1. Clica em `Browse files`.
2. Seleciona um `.zip`, `.gpx`, `.fit`, `.tcx`, `.gz` ou `.git`.
3. Se for ficheiro individual, escolhe o tipo em `Type for single activity files`.
4. Mantém `Import only new activities` ativo para importar apenas novidades.
5. Clica em `Import Uploaded File`.

No fim, a app mostra um resumo:

```text
loaded=1, skipped=0, failed=0, streams=3256, metrics=711, recommendations=11
```

Significado:

- `loaded`: atividades novas importadas.
- `skipped`: atividades já existentes ignoradas.
- `failed`: atividades que falharam.
- `streams`: pontos GPS importados.
- `metrics`: métricas recalculadas.
- `recommendations`: recomendações geradas.

O ficheiro enviado é temporário. A app importa, otimiza a base com `VACUUM`/`CHECKPOINT` e apaga o ficheiro de upload no fim.

## 5. Filtros temporais

Na sidebar, podes filtrar por:

- anos
- meses
- intervalo de datas
- tipos de atividade

Estes filtros afetam o overview, timeline, estatística, mapas, heatmaps e lista de atividades.

## 6. Overview detalhado

A página `Overview` mostra:

- total de atividades
- distância total
- tempo em movimento
- calorias
- ganho de elevação
- performance média
- projeção para o ano corrente
- tendência dos últimos 30 dias contra os 30 dias anteriores
- distância mensal
- tempo por tipo de atividade
- calorias e elevação por mês
- tendência de performance
- composição por tipo e intensidade
- relação distância vs performance

## 7. Projeção do ano corrente

Na secção `Current Year Projection`, a app calcula:

- distância YTD
- tempo YTD
- calorias YTD
- ganho de elevação YTD
- performance média YTD
- projeção anual com base no ritmo atual

A projeção usa os dias já decorridos no ano corrente para estimar o total anual se o ritmo se mantiver.

## 8. Timeline

Na página `Timeline` podes ver:

- distância por ano
- performance média por ano
- tempo e elevação por ano
- distância anual por tipo de atividade
- variação year-over-year
- distância mensal por tipo
- frequência e performance por dia da semana

## 9. Estatística

Na página `Statistics` existem análises estatísticas complementares:

- média
- mediana
- percentis 25 e 75
- mínimo e máximo
- desvio padrão
- boxplots de performance por tipo
- distribuição de duração
- heart rate vs performance
- distribuição de pace por tipo
- matriz de correlação entre métricas

## 10. Mapas GPS por área

Na página `Geo Map` podes ver:

- zonas onde passas mais vezes
- zonas com melhor performance média
- velocidade média por zona
- heart rate médio por zona
- tabela com as principais áreas GPS

O mapa usa agregação por células geográficas para evitar carregar todos os pontos GPS crus na interface.

## 11. Heatmaps

Na página `Heatmaps` existem dois mapas:

- `Run heatmap by week`
- `Ride heatmap by week`

Cada célula representa quilómetros por dia da semana e semana ISO.

## 12. Detalhe por atividade

Na página `Activities` podes:

- filtrar por tipo
- mostrar só atividades com GPS
- escolher uma atividade específica
- ver distância, tempo, velocidade, pace e performance
- ver mapa GPS
- ver gráficos de elevação, pace, velocidade e heart rate

Algumas atividades podem não ter stream GPS, dependendo do ficheiro exportado.

## 13. Atualização por linha de comando

Para importar um export completo sem abrir a app:

```bash
python3 scripts/import_strava_export.py /caminho/export.zip --only-new
```

Para reprocessar tudo, remove `--only-new`.

## 14. Boas práticas

- Usa `Import only new activities` para uploads regulares.
- Mantém a base DuckDB fora do Git.
- Não guardes `.env`, tokens OAuth, exports Strava ou ficheiros de atividade no repositório.
- Usa `.zip` quando quiseres atualizar histórico em lote.
- Usa `.gpx`, `.fit` ou `.tcx` quando quiseres adicionar apenas uma atividade.
- Depois de um upload grande, espera a mensagem final antes de navegar no dashboard.

