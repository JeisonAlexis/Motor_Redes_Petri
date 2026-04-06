# petri-matrix-studio

Motor de redes de Petri con editor gráfico basado en la formulación matricial clásica:

- transición habilitada: `μ >= e[j] · D⁻`
- disparo de la transición `j`: `μ' = μ + e[j] · D`
- con `D = D⁺ - D⁻`

<div style="text-align:center; margin-bottom:15px;">
  <a href="https://jeisonalexis.github.io/documentosPages/petri.html" target="_blank">
    📄 Informe Tecnico Trabajo Motor de Redes de Petri
  </a>
</div>

## Instalación

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e .
```

## Ejecución

```bash
petri-matrix-studio
```

## Uso rápido

1. Use la barra superior para escoger una herramienta.
2. Agregue lugares y transiciones sobre el lienzo.
3. Cree arcos desde lugar→transición o transición→lugar.
4. Seleccione un lugar para editar su número de tokens.
5. Guarde la red en JSON.
6. En modo selección, haga clic sobre una transición habilitada para dispararla.

## Formato JSON

```json
{
  "version": 1,
  "name": "Mi red",
  "places": [
    {"id": "P1", "label": "P1", "x": 120, "y": 180, "tokens": 1}
  ],
  "transitions": [
    {"id": "T1", "label": "T1", "x": 300, "y": 180}
  ],
  "arcs": [
    {"source": "P1", "target": "T1", "weight": 1}
  ]
}
```


