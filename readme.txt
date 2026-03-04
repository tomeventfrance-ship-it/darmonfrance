version: 2026-03
creators:
  min_diamonds: 100000
  levels:
  - name: Niveau 1
    base: 100000
  - name: Niveau 2
    base: 200000
  - name: Niveau 3
    base: 300000
  - name: Niveau 4
    base: 500000
  - name: Niveau 5
    base: 700000
  - name: Niveau 6
    base: 1000000
  - name: Niveau 7
    base: 1600000
  - name: Niveau 8
    base: 2500000
  - name: Niveau 9
    base: 5000000
  activity_tiers:
  - label: 11j/30h
    days: 11
    hours: 30
    rate: 0.01
  - label: 18j/60h
    days: 18
    hours: 60
    rate: 0.02
  - label: 22j/80h
    days: 22
    hours: 80
    rate: 0.03
  bonus:
    non_cumulative: true
    evolution:
      condition: passage au palier supérieur vs mois précédent
      rate_add: 0.02
    stagnation:
      condition: déjà dépassé 200K (même hors agence) et même palier
      rate_add: 0.01
    down:
      condition: en baisse vs mois précédent
      rate_add: 0.0
  fixed_rewards_50k:
    enabled: true
    min_diamonds: 50000
    apply_only_if_below_min_diamonds: true
    rules:
    - condition: '>=11j & >=30h'
      reward: 500
    - condition: '>=22j & >=80h'
      reward: 1000
  rounding:
    type: floor
    step: 1000
agents:
  min_diamonds: 200000
  non_reportable: true
  task_progressive:
    options:
    - task: 5%
      commission: 0.015
    - task: 7%
      commission: 0.02
    - task: 9%
      commission: 0.025
  bonus_backstage:
    non_cumulative: true
    options:
    - label: 0%
      rate_add: 0.0
    - label: +0,5%
      rate_add: 0.005
    - label: +1%
      rate_add: 0.01
  rounding:
    type: floor
    step: 100
managers:
  min_diamonds: 1000000
  non_reportable: true
  task_progressive:
    options:
    - task: 5%
      commission: 0.02
    - task: 7%
      commission: 0.03
    - task: 9%
      commission: 0.04
  bonus_backstage:
    non_cumulative: true
    options:
    - label: 0%
      rate_add: 0.0
    - label: +0,5%
      rate_add: 0.005
    - label: +1%
      rate_add: 0.01
  rounding:
    type: floor
    step: 100
