import argparse

from flexfl.builtins.Results import Results


def plot(folder: str, visualize: bool = False, force: bool = False):
    try:
        r = Results(folder)
        if force or not r.has_results():
            print(f"Analyzing folder: {folder}")
            r.plot_all(visualize)
        else:
            print(f"Results already exist in {folder}. Use --force to overwrite.")
    except Exception as e:
        print(f"Error: {e}")
        return


def main():
    parser = argparse.ArgumentParser(description="Analyze results")
    parser.add_argument("-r", "--results", type=str, help="Results folder (\"all\" to preprocess all folders), otherwise the last folder is chosen", default="all")
    parser.add_argument("-d", "--dir", type=str, help="Base folder name", default="results")
    parser.add_argument("-v", "--visualize", action="store_true", help="Visualize the results", default=False)
    parser.add_argument("-f", "--force", action="store_true", help="Force", default=False)
    args = parser.parse_args()
    Results.BASE_DIR = args.dir
    if args.results is None:
        folder = Results.get_last_folder()
        if folder is None:
            print("No folder found.")
            return
        plot(folder, args.visualize, args.force)
    elif args.results == "all":
        folder = Results.get_all_folders()
        for f in folder:
            plot(f, args.visualize, args.force)
    else:
        plot(args.results, args.visualize, args.force)
    print("Done!")


if __name__ == "__main__":
    main()