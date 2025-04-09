import argparse

from flexfl.builtins.Results import Results


def plot(folder: str, visualize: bool = False):
    try:
        print(f"Analyzing folder: {folder}")
        r = Results(folder)
        r.plot_all(visualize)
    except Exception as e:
        print(f"Error: {e}")
        return


def main():
    parser = argparse.ArgumentParser(description="Analyze results")
    parser.add_argument("-r", "--results", type=str, help="Results folder (\"all\" to preprocess all folders), otherwise the last folder is chosen", default=None)
    parser.add_argument("-f", "--folder", type=str, help="Base folder name", default="results")
    parser.add_argument("-v", "--visualize", action="store_true", help="Visualize the results", default=False)
    args = parser.parse_args()
    Results.BASE_DIR = args.folder
    if args.results is None:
        folder = Results.get_last_folder()
        if folder is None:
            print("No folder found.")
            return
        plot(folder, args.visualize)
    elif args.results == "all":
        folder = Results.get_all_folders()
        for f in folder:
            plot(f, args.visualize)
    else:
        plot(args.results, args.visualize)
    print("Done!")


if __name__ == "__main__":
    main()