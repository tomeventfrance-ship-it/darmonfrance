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
    evolution_rate_add: 0.02
    stagnation_rate_add: 0.01
  fixed_rewards_50k:
    min_diamonds: 50000
    reward_11_30: 500
    reward_22_80: 1000
  rounding_step: 1000
agents:
  min_diamonds: 200000
  task_progressive:
    5%: 0.015
    7%: 0.02
    9%: 0.025
  bonus_choices:
    0%: 0.0
    +0,5%: 0.005
    +1%: 0.01
  rounding_step: 100
  facture_rate: 0.0084
managers:
  min_diamonds: 1000000
  task_progressive:
    5%: 0.02
    7%: 0.03
    9%: 0.04
  bonus_choices:
    0%: 0.0
    +0,5%: 0.005
    +1%: 0.01
  rounding_step: 100
  facture_rate: 0.0084
