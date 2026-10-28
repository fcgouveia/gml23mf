# gml23mf

Converte um grafo em formato **GML** (por exemplo, uma rede de coocorrência exportada do VOSviewer) em um arquivo **3MF** para impressão 3D multicor.

- Cada **nó** vira uma esfera, com raio proporcional ao seu grau.
- Cada **aresta** vira um cilindro, com espessura proporcional ao peso.
- Cada **cluster** vira um objeto separado no 3MF, para você atribuir um filamento por cluster no fatiador.
- O eixo **Z** pode representar um atributo numérico dos nós (por padrão, o ano médio de publicação), normalizado para ficar proporcional a X e Y.

## Requisitos

- Python 3.9 ou superior
- `networkx`, `trimesh` e `numpy`

```bash
pip install networkx trimesh numpy
```

## Uso

```bash
python gml23mf.py rede.gml modelo.3mf
```

Com opções:

```bash
python gml23mf.py rede.gml modelo.3mf --cluster-attr cluster --z-attr score_avg_pub_year --z-ratio 0.5
```

Se os argumentos forem omitidos, o script usa `2Dgraph.gml` como entrada e `3Dgraph.3mf` como saída.

Ao terminar, ele imprime as dimensões do modelo e um resumo dos objetos gerados (nome, cor e número de nós), por exemplo:

```
Extensão X/Y: 200.0 mm | Z: score_avg_pub_year de 2015.5 a 2023 -> 0 a 100.0 mm
Gerado modelo.3mf. Um objeto por cluster (atribua um filamento a cada):
  cluster_1                        #f25454  34 nós
  cluster_2                        #54f2f2  21 nós
  arestas_entre_clusters           #888888  0 nós
```

## Opções

| Opção | Padrão | Descrição |
|---|---|---|
| `--cluster-attr` | `cluster` | Atributo do nó que define o cluster. |
| `--z-attr` | `score_avg_pub_year` | Atributo do nó usado no eixo Z. |
| `--z-ratio` | `1.0` | Altura total em Z como fração da maior extensão entre X e Y. Use valores menores (por exemplo, `0.5`) para um modelo mais achatado. |
| `--scale-xy` | `50` | Fator aplicado às coordenadas `x` e `y` do GML, que define o tamanho do modelo. |
| `--node-scale` | `0.2` | Raio da esfera = grau do nó × este valor. |
| `--min-radius` | `0.5` | Raio mínimo das esferas, para nós de grau 0 ou muito baixo. |
| `--edge-scale` | `0.6` | Espessura das arestas = peso^0,2 × este valor. |
| `--edge-color` | `#888888` | Cor das arestas entre clusters diferentes (pré-visualização). |
| `--subdiv` | `2` | Resolução das esferas. Valores maiores geram arquivos maiores. |

## Formato de entrada

O script espera um GML em que cada nó tenha:

- `x` e `y`: posição do nó no layout 2D.
- `cluster` (ou o atributo indicado em `--cluster-attr`): identificador do cluster. Nós sem esse atributo vão para `cluster_sem_cluster`.
- O atributo de Z (por padrão, `score<avg._pub._year>`), um número.
- Opcionalmente, `degree` (se ausente, o grau é calculado a partir do grafo) e `color` em hexadecimal (`#RRGGBB`), usado como cor do cluster.

Nas arestas, o peso é lido de `value` ou `weight` (padrão 1 se ausente).

### Chaves inválidas do VOSviewer

O VOSviewer exporta GML com chaves como `<links>`, `<total link strength>` ou `score<avg._pub._year>`, que não são GML válido e fazem o `networkx` falhar. O script corrige isso antes de ler o arquivo:

| No arquivo | Vira |
|---|---|
| `<links>` | `links` |
| `<total link strength>` | `total_link_strength` |
| `score<avg._pub._year>` | `score_avg_pub_year` |

Textos entre aspas, como títulos e rótulos, não são alterados. O arquivo é lido como UTF-8.

## Como o eixo Z é calculado

1. X e Y são as coordenadas do GML multiplicadas por `--scale-xy`.
2. O menor valor do atributo de Z vai para Z = 0 e o maior vai para Z = (maior extensão entre X e Y) × `--z-ratio`.
3. Nós sem o atributo ficam no valor médio. Se nenhum nó tiver o atributo, o script avisa, lista os atributos disponíveis e usa Z = 0.

Assim, com `--z-ratio 1.0`, o modelo tem a mesma altura que a maior dimensão do plano.

## Saída e impressão multicor

O `.3mf` contém:

- Um objeto `cluster_<valor>` por cluster, com as esferas dos nós e as arestas internas ao cluster.
- Um objeto `arestas_entre_clusters`, com as arestas que ligam clusters diferentes.

Cada objeto traz uma cor embutida, usada na pré-visualização. Para imprimir, abra o `.3mf` no seu fatiador (PrusaSlicer, OrcaSlicer, Bambu Studio e similares) e atribua um filamento a cada objeto.

Os objetos são esferas e cilindros que se sobrepõem. Confira a malha no fatiador antes de imprimir e ajuste a escala para o tamanho da sua mesa de impressão (`--scale-xy`).

## Solução de problemas

- **`cannot tokenize ...`**: o GML tem alguma sintaxe que o script não reconheceu. Ele imprime as primeiras linhas do arquivo já corrigido. Abra uma issue com essa saída.
- **`AVISO: atributo '...' não encontrado`**: o nome do atributo de Z ou de cluster é diferente. Use `--z-attr` ou `--cluster-attr` com um dos nomes listados no aviso.
- **Modelo grande ou alto demais**: reduza `--scale-xy` ou use um `--z-ratio` menor.

## Licença

Defina a licença do projeto antes de publicar (por exemplo, MIT).
