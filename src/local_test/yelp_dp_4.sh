#!/bin/bash
#SBATCH --job-name CoLA Finetuned             # 任务名叫 example
#SBATCH --gres gpu:a100:1                   # 每个子任务都用一张 A100 GPU
#SBATCH --time 3-1:00:00                    # 子任务 1 天 1 小时就能跑完

echo 'Yelp DP 4encoder'

# python main_pipeline_llm_4.py --seed 60 --configs yelp_wo_4

# 50
python main_pipeline_llm_4.py --seed 60 --configs yelp_dp_4

# 70
sed -i 's/"epsilon": 50/"epsilon": 70/g' ./configs/yelp_dp_4.json
python main_pipeline_llm_4.py --seed 60 --configs yelp_dp_4

# 90
sed -i 's/"epsilon": 70/"epsilon": 90/g' ./configs/yelp_dp_4.json
python main_pipeline_llm_4.py --seed 60 --configs yelp_dp_4

# 100
sed -i 's/"epsilon": 90/"epsilon": 100/g' ./configs/yelp_dp_4.json
python main_pipeline_llm_4.py --seed 60 --configs yelp_dp_4

# 500
sed -i 's/"epsilon": 100/"epsilon": 500/g' ./configs/yelp_dp_4.json
python main_pipeline_llm_4.py --seed 60 --configs yelp_dp_4

sed -i 's/"epsilon": 500/"epsilon": 50/g' ./configs/yelp_dp_4.json

for seed in {61,62,63,64,65}
    do
        
    python main_pipeline_llm_4.py --seed $seed --configs yelp_wo_4

    # 50
    python main_pipeline_llm_4.py --seed $seed --configs yelp_dp_4

    # 70
    sed -i 's/"epsilon": 50/"epsilon": 70/g' ./configs/yelp_dp_4.json
    python main_pipeline_llm_4.py --seed $seed --configs yelp_dp_4

    # 90
    sed -i 's/"epsilon": 70/"epsilon": 90/g' ./configs/yelp_dp_4.json
    python main_pipeline_llm_4.py --seed $seed --configs yelp_dp_4

    # 100
    sed -i 's/"epsilon": 90/"epsilon": 100/g' ./configs/yelp_dp_4.json
    python main_pipeline_llm_4.py --seed $seed --configs yelp_dp_4

    # 500
    sed -i 's/"epsilon": 100/"epsilon": 500/g' ./configs/yelp_dp_4.json
    python main_pipeline_llm_4.py --seed $seed --configs yelp_dp_4

    sed -i 's/"epsilon": 500/"epsilon": 50/g' ./configs/yelp_dp_4.json
done