fn main() {
    println!(
        "{{\"native_game_bytes\":{},\"enemy_state_bytes\":{},\"enemy_vec_bytes\":{}}}",
        std::mem::size_of::<dodge_core::NativeGame>(),
        std::mem::size_of::<dodge_core::EnemyState>(),
        std::mem::size_of::<Vec<dodge_core::EnemyState>>(),
    );
}
