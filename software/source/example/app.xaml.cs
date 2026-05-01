//------------------------------------------------------------------------------
// <copyright file="app.xaml.cs" company="Microsoft">
//     Copyright (c) Microsoft Corporation.  All rights reserved.
// </copyright>
//------------------------------------------------------------------------------

namespace Microsoft.Samples.Kinect.KinectExplorer
{
    using System;
    using System.Windows;
    using System.Windows.Threading;

    public partial class App : Application
    {
        public App()
        {
            DispatcherUnhandledException += (s, e) => {
                try {
                    System.IO.File.AppendAllText("error.log", DateTime.Now + " ERROR: " + e.Exception.Message + "\n" + e.Exception.StackTrace + "\n\n");
                } catch {}
                e.Handled = true;
            };
        }

        private void Application_Startup(object sender, StartupEventArgs e)
        {
        }
    }
}
