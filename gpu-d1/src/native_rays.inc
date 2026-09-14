// Access native precomputed ray bitsets in the isolated los.cc.
void gpu_export_rays(const char *path);
void gpu_export_rays(const char *path) {
    raycast();
    FILE *f = fopen(path, "w");
    fprintf(f, "%zu\n", cellray_ends.size());
    for (unsigned i = 0; i < cellray_ends.size(); i++)
        fprintf(f, "%d %d\n", cellray_ends[i].x, cellray_ends[i].y);
    circle_def bounds;
    for (int y = 0; y <= 8; y++)
        for (int x = 0; x <= 8; x++) {
            fprintf(f, "%d %d %d ", x, y, bounds.contains(coord_def(x, y)) ? 1 : 0);
            for (unsigned i = 0; i < cellray_ends.size(); i++)
                fputc(blockrays(coord_def(x, y))->get(i) ? '1' : '0', f);
            fputc('\n', f);
        }
    fclose(f);
}
