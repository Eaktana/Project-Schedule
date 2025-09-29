def run_genetic_algorithm(
    data: Dict[str, pd.DataFrame],
    generations,
    pop_size,
    elite_size: int = 3,
    cx_rate: float = 0.9,
    mut_rate: float = 0.2,
    seed: int = 42,
):
    rng = random.Random(seed)

    courses = data["courses"]
    ga_free = data["ga_free"]

    # 1) ประชากรเริ่มต้น
    _chk_cancel()
    population = initialize_population(courses, ga_free, pop_size, seed=seed)

    # 2) helpers
    allow_set = set(
        (
            int(r["group_id"]) if pd.notna(r["group_id"]) else None,
            r["day_of_week"],
            r["start_time"],
            r["stop_time"],
            r["room"],
        )
        for _, r in ga_free.iterrows()
    )
    _chk_cancel()

    room_type_of = dict(
        (r["room"], r["room_type"])
        for _, r in ga_free.drop_duplicates(subset=["room"]).iterrows()
    )

    def fitness(ind):
        return evaluate_individual(ind, allow_set, room_type_of)

    # ป้องกันกรณีไม่มีประชากร
    if not population:
        return {"fitness": float("-inf"), "schedule": []}

    # 3) วน GA
    for _ in range(generations):
        _chk_cancel()

        scored = [(fitness(ind), ind) for ind in population]
        _chk_cancel()

        scored.sort(key=lambda x: x[0], reverse=True)
        # print(f"Gen {_}: best fitness = {scored[0][0]}")

        # เก็บตัวท็อปไว้ (elitism)
        new_pop = [scored[i][1] for i in range(min(elite_size, len(scored)))]

        # สร้างลูก
        parent_pool = [ind for _, ind in scored[: max(10, pop_size)]]
        while len(new_pop) < pop_size and parent_pool:
            _chk_cancel()
            p1, p2 = rng.sample(parent_pool, 2)
            if rng.random() < cx_rate:
                child = crossover(p1, p2, allow_set, ga_free, rng, room_type_of)
            else:
                child = [dict(g) for g in (p1 if rng.random() < 0.5 else p2)]
            child = mutate(child, allow_set, ga_free, mut_rate, rng, room_type_of)
            new_pop.append(child)

        population = new_pop

    _chk_cancel()
    # 4) สรุปผล
    scored = [(fitness(ind), ind) for ind in population]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_fitness, best_ind = scored[0]
    return {"fitness": best_fitness, "schedule": best_ind}
