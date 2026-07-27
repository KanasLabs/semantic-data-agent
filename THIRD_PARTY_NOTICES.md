# Third-Party Data And Benchmark Notices

The repository's original source code and documentation are available under
the root [`LICENSE`](LICENSE). Third-party datasets, benchmark-derived
artifacts, names, and trademarks remain subject to their respective terms and
are not relicensed by the repository's MIT license.

## BIRD Mini-Dev

The following committed materials contain selected or transformed BIRD
Mini-Dev questions, evidence, SQL, review classifications, schema descriptions,
or controlled onboarding evidence:

```text
data/evals/audits/bird_mini_dev_*.jsonl
data/evals/cases/bird_mini_dev_*.jsonl
data/wren/starrocks_bird_debit_card_specializing_wren_project/
```

Upstream sources:

- BIRD project: <https://bird-bench.github.io/>
- BIRD Mini-Dev repository: <https://github.com/bird-bench/mini_dev>
- BIRD Mini-Dev dataset: <https://huggingface.co/datasets/birdsql/bird_mini_dev>
- License: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)

The adapted BIRD materials listed above remain available under CC BY-SA 4.0.
The repository does not commit the downloaded BIRD database package; local
downloads live under the Git-ignored `data/external/` directory.

Project-authored evaluation and integration documentation that references BIRD
remains under the repository's MIT license and links back to the upstream
project and dataset.

Suggested citation:

```bibtex
@article{li2024can,
  title={Can LLM Already Serve as a Database Interface? A Big Bench for Large-Scale Database Grounded Text-to-SQLs},
  author={Li, Jinyang and Hui, Binyuan and Qu, Ge and Yang, Jiaxi and Li, Binhua and Li, Bowen and Wang, Bailin and Qin, Bowen and Geng, Ruiying and Huo, Nan and others},
  journal={Advances in Neural Information Processing Systems},
  volume={36},
  year={2024}
}
```

## jaffle_shop Demo

The `jaffle_shop` names, schema, and demo workflow are based on public
quickstart/demo materials from WrenAI and dbt Labs:

- WrenAI: <https://github.com/Canner/WrenAI>
- dbt Labs jaffle-shop: <https://github.com/dbt-labs/jaffle-shop>

These materials are used only as local demonstration and evaluation fixtures.
Refer to the upstream projects for their applicable terms.

## TPC-H Demo

The TPC-H project files contain a small synthetic development fixture based on
the TPC-H schema and terminology. They are not official benchmark results and
must not be represented as audited TPC performance claims.

- TPC-H information: <https://www.tpc.org/tpch/>

TPC, TPC-H, and related marks belong to the Transaction Processing Performance
Council. The repository's MIT license does not grant rights to third-party
marks.
