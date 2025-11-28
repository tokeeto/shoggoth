import jpype
import jpype.imports
from shoggoth.files import asset_dir

def run_conversion(java_path, jar_path, project_path, output_path):
    if not jar_path:
        raise Exception("Path to Strange Eons jar file not set. Press F1 and change the settings. This needs to be the .jar file - other versions won't work.")

    # start the JVM to make further imports available
    jpype.startJVM(
        java_path or jpype.getDefaultJVMPath(),
        f'-javaagent:{jar_path}',
        classpath=[f'{jar_path}'],
    )

    # import the JVM generated imports
    from shoggoth import strange_eons_parser
    from ca.cgjennings.apps.arkham import StrangeEons
    import javax
    import java
    from java.io import File


    # start SE in headless mode
    # This is using the keep-alive script to prevent it from shutting down
    # while we run our python stuff
    StrangeEons.main([
        '--run',
        str(asset_dir / 'js' / 'KeepAlive.js')
    ])

    # all script interactions must happen in a non-main thread
    @jpype.JImplements(java.lang.Runnable)
    class Launch:
        @jpype.JOverride
        def run(self):
            # for readability, we have our function elsewhere
            strange_eons_parser.run_import(project_path, output_path)

    # now run the class in a new thread
    javax.swing.SwingUtilities.invokeAndWait(Launch())

    # and now that we're done, we terminate the JVM
    # this will forcefully kill SE, despite the script
    # preventing it from closing.
    print('Done running strange_eons.py')
    return
